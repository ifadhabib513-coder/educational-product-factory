"""Research pipeline — deterministic stage assembly and evidence extraction.

The pipeline owns everything that does not need a model: collecting results,
normalising, deduplicating, ranking, and resolving into a report. Claim
*extraction* from page text is the model's job (the Research crew); everything
here is reproducible given the same provider responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from lpf.domain.identity import new_id
from lpf.research.audience import AudienceLevel, classify_audience
from lpf.research.authority import authority_rank
from lpf.research.intent import QueryIntent, classify_intent
from lpf.research.relevance import effective_relevance
from lpf.research.scoring import confidence as confidence_for
from lpf.research.scoring import date_span, ranking_score
from lpf.research.service import ResearchService
from lpf.schemas.research import (
    ConflictReport,
    EvidenceClaim,
    EvidenceMap,
    KnowledgeGap,
    ResearchQuestion,
    ResearchReport,
    SearchResult,
    VerifiedSource,
)

logger = logging.getLogger(__name__)

# Below this, a URL is treated as low-value content (and often a redirect stub).
_MIN_SNIPPET_CHARS = 40


def canonical_url(url: str) -> str:
    """Normalise a URL for deduplication.

    Strips the fragment, lowercases scheme and host, drops a leading ``www.``,
    and removes a trailing slash. Query strings are preserved because for some
    providers the query is the identifier, not a filter.
    """
    if not url:
        return ""

    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


@dataclass
class PipelineConfig:
    """Tunables for the deterministic pipeline."""

    max_results_per_question: int = 20
    max_sources: int = 60
    relevance_threshold: float = 0.5
    #: Authorities below this rank are discarded as evidence.
    min_authority_rank: int = 1
    #: Number of independent sources a claim needs before it is considered supported.
    min_sources_per_claim: int = 1
    conflict_window: int = 60

    #: Reader level, normally threaded down from ``LearnerProfile.level``.
    audience_level: AudienceLevel = AudienceLevel.INTERMEDIATE
    #: Forces a single intent instead of classifying each question. Intended for
    #: tests and for callers that already know the intent.
    intent_override: QueryIntent | None = None


@dataclass
class PipelineResult:
    """Everything the pipeline produced, for the report and for QA."""

    report: ResearchReport
    results: list[SearchResult] = field(default_factory=list)
    duplicates_removed: int = 0
    dropped_low_authority: int = 0
    dropped_thin: int = 0


class ResearchPipeline:
    """Assemble raw search results into a verified, ranked ResearchReport."""

    def __init__(
        self,
        service: ResearchService,
        config: PipelineConfig | None = None,
        *,
        audience: AudienceLevel | str | None = None,
    ) -> None:
        self._service = service
        self._config = config or PipelineConfig()
        if audience is not None:
            self._config.audience_level = classify_audience(audience)
        self._intent: QueryIntent | None = self._config.intent_override
        self._query = ""
        self._newest = 0.0
        self._oldest = 0.0
        #: When a run id is supplied, generated ids become deterministic
        #: (``<run_id>-claim-0001``) so two identical runs produce identical
        #: reports. Without a run id, ids fall back to uuid4.
        self._run_id: str | None = None
        self._claim_seq = 0

    def _claim_id(self) -> str:
        """Deterministic claim id when running under a run id, else a uuid."""
        self._claim_seq += 1
        if self._run_id is not None:
            return f"{self._run_id}-claim-{self._claim_seq:04d}"
        return new_id()

    def _scoped_id(self, kind: str) -> str:
        """Deterministic single-instance id when running under a run id."""
        if self._run_id is not None:
            return f"{self._run_id}-{kind}-0001"
        return new_id()

    def resolve_intent(self, questions: list[ResearchQuestion]) -> QueryIntent:
        """Intent for this run: an override, else the first classified question.

        A run is scored as one intent rather than per result. Scoring a mixed
        batch under several intents would make the ranking order depend on which
        question happened to be processed first.
        """
        if self._config.intent_override is not None:
            return self._config.intent_override
        for question in questions:
            return classify_intent(question.text)
        return QueryIntent.GENERAL

    async def run(
        self,
        product_spec_id: str,
        questions: list,
        *,
        run_id: str | None = None,
    ) -> PipelineResult:
        """Execute searches for ``questions`` and build a ResearchReport."""
        self._run_id = run_id
        self._claim_seq = 0
        raw_by_question = await self._service.execute_plan_questions(questions)

        self._intent = self.resolve_intent(questions)
        self._query = " ".join(q.text for q in questions)

        collected: list[SearchResult] = []
        for results in raw_by_question.values():
            collected.extend(self._derive_relevance(results, questions))

        self._oldest, self._newest = date_span(collected)

        deduped, duplicate_count = self.deduplicate(collected)
        qualified, low_auth, thin = self.filter_sources(deduped)
        ranked = self.rank(qualified)[: self._config.max_sources]

        verified = [self._verify(r) for r in ranked]
        claims = self._build_claims(ranked)
        conflicts = self.detect_conflicts(claims)
        gaps = self.identify_gaps(questions, raw_by_question)

        report = ResearchReport(
            id=self._scoped_id("research_report"),
            product_spec_id=product_spec_id,
            claims=claims,
            verified_sources=[v for v in verified if v is not None],
            conflicts=conflicts,
            knowledge_gaps=gaps,
            source_refs=[v.source_id for v in verified if v is not None],
        )

        logger.info(
            "Research pipeline (intent=%s, audience=%s): %d raw, %d duplicates, "
            "%d low-authority, %d thin, %d kept",
            self._intent,
            self._config.audience_level,
            len(collected),
            duplicate_count,
            low_auth,
            thin,
            len(ranked),
        )

        return PipelineResult(
            report=report,
            results=ranked,
            duplicates_removed=duplicate_count,
            dropped_low_authority=low_auth,
            dropped_thin=thin,
        )

    # -- stages ------------------------------------------------------------

    def deduplicate(self, results: list[SearchResult]) -> tuple[list[SearchResult], int]:
        """Collapse results sharing a canonical URL, keeping the best-ranked.

        When several providers return the same page, the higher-authority copy
        wins so the retained result is the one worth citing.
        """
        best: dict[str, SearchResult] = {}
        duplicates = 0

        for result in results:
            key = canonical_url(result.url) or result.source_id
            existing = best.get(key)

            if existing is None:
                best[key] = result
                continue

            duplicates += 1
            if self._score(result) > self._score(existing):
                best[key] = result

        return list(best.values()), duplicates

    def filter_sources(self, results: list[SearchResult]) -> tuple[list[SearchResult], int, int]:
        """Drop sources that are too thin or too low-authority to cite."""
        kept: list[SearchResult] = []
        low_auth = 0
        thin = 0

        for result in results:
            if len(result.snippet.strip()) < _MIN_SNIPPET_CHARS:
                thin += 1
                continue
            if authority_rank(result.authority) < self._config.min_authority_rank:
                low_auth += 1
                continue
            kept.append(result)

        return kept, low_auth, thin

    @staticmethod
    def _derive_relevance(
        results: list[SearchResult],
        questions: list[ResearchQuestion],
    ) -> list[SearchResult]:
        """Fill in relevance for providers that report none.

        Only Tavily returns a backend score; arXiv, Wikimedia and SearXNG leave
        ``relevance_score`` at 0.0. Without this, claim confidence for those
        providers could never exceed ``authority_weight`` and every real report
        produced an empty EvidenceMap. See ``research/relevance.py``.
        """
        if not questions:
            return results

        query = " ".join(q.text for q in questions)

        return [
            result
            if result.relevance_score > 0.0
            else result.model_copy(
                update={
                    "relevance_score": effective_relevance(
                        query,
                        provider_score=result.relevance_score,
                        title=result.title,
                        snippet=result.snippet,
                    )
                }
            )
            for result in results
        ]

    def rank(self, results: list[SearchResult]) -> list[SearchResult]:
        """Order results by intent-conditional ranking score."""
        return sorted(results, key=self._score, reverse=True)

    def _score(self, result: SearchResult) -> float:
        """Ranking score: a preference order for this intent and audience.

        Falls back to the legacy authority-weighted score when the run has not
        been initialised through ``run()``, so direct calls into ``rank`` in
        isolation still order sensibly.
        """
        if self._intent is None:
            auth = authority_rank(result.authority) / 7.0
            return auth * 0.4 + result.relevance_score * 0.6

        return ranking_score(
            result,
            query=self._query,
            intent=self._intent,
            audience=self._config.audience_level,
            oldest=self._oldest,
            newest=self._newest,
        )

    def _verify(self, result: SearchResult) -> VerifiedSource | None:
        """Build a VerifiedSource, marking unverified results rather than dropping them.

        A source that resolved but is thin is recorded with ``relevant=False``
        so the evidence map can show what was found and rejected.
        """
        if not result.url:
            return None

        return VerifiedSource(
            source_id=result.source_id,
            url=result.url,
            title=result.title,
            domain=result.domain,
            authority=result.authority,
            exists=True,
            accessible=True,
            relevant=result.relevance_score >= self._config.relevance_threshold,
        )

    def _build_claims(self, results: list[SearchResult]) -> list[EvidenceClaim]:
        """Promote each retained source into a citable claim.

        One claim per source: a claim spanning several sources would merge
        statements that may not agree, and the conflict detector works on
        claim granularity.

        Claim confidence uses the evidence score rather than the ranking score.
        Confidence has to stay comparable across intents for the EvidenceMap
        support threshold to mean the same thing every run.
        """
        claims: list[EvidenceClaim] = []
        for result in results:
            if len(result.snippet.strip()) < _MIN_SNIPPET_CHARS:
                continue

            if self._intent is None:
                confidence = round(min(1.0, self._score(result)), 4)
            else:
                confidence = confidence_for(result, query=self._query, intent=self._intent)

            claims.append(
                EvidenceClaim(
                    claim_id=self._claim_id(),
                    claim=result.snippet.strip(),
                    source_ids=[result.source_id],
                    evidence_text=result.snippet.strip(),
                    confidence=confidence,
                    claim_type="factual",
                    notes=f"Retrieved from {result.domain} via {result.provider.value}.",
                )
            )
        return claims

    def detect_conflicts(self, claims: list[EvidenceClaim]) -> list[ConflictReport]:
        """Flag claims whose text diverges on shared subject matter.

        Deliberately conservative: near-identical wording is agreement, not
        conflict, and a false conflict would send the Revision crew chasing a
        disagreement that does not exist.
        """
        reports: list[ConflictReport] = []
        window = self._config.conflict_window

        for i, left in enumerate(claims):
            for right in claims[i + 1 : i + window]:
                if self._contradicts(left.claim, right.claim):
                    reports.append(
                        ConflictReport(
                            claim_ids=[left.claim_id, right.claim_id],
                            description=(
                                "Sources make similar claims with divergent wording; "
                                "review both before relying on either."
                            ),
                            severity="info",
                        )
                    )

        return reports

    @staticmethod
    def _contradicts(left: str, right: str) -> bool:
        """Heuristic divergence check.

        Requires substantial lexical overlap *and* differing polarity. Low
        overlap means unrelated text, not a conflict.
        """
        left_tokens = _tokens(left)
        right_tokens = _tokens(right)
        if not left_tokens or not right_tokens:
            return False

        overlap = len(left_tokens & right_tokens)
        smaller = min(len(left_tokens), len(right_tokens))
        if smaller == 0 or overlap / smaller < 0.5:
            return False

        return _polarity(left) != _polarity(right)

    def identify_gaps(
        self,
        questions: list,
        results_by_question: dict[str, list[SearchResult]],
    ) -> list[KnowledgeGap]:
        """Report questions that returned nothing usable.

        A question with no results at all is a high-impact gap: the content crew
        will have nothing to build that section from.
        """
        gaps: list[KnowledgeGap] = []

        for question in questions:
            found = results_by_question.get(question.question_id) or []
            if not found:
                gaps.append(
                    KnowledgeGap(
                        topic=getattr(question, "topic", "unknown"),
                        description=f"No sources found for: {question.text}",
                        impact="high",
                    )
                )
        return gaps

    # -- evidence map ------------------------------------------------------

    def to_evidence_map(
        self,
        report: ResearchReport,
        *,
        confidence_threshold: float = 0.7,
    ) -> EvidenceMap:
        """Build the EvidenceMap the content crew consumes."""
        supported = [c for c in report.claims if c.confidence >= confidence_threshold]
        conflicting_ids = {cid for c in report.conflicts for cid in c.claim_ids}

        return EvidenceMap(
            id=self._scoped_id("evidence_map"),
            research_report_id=report.id,
            claims=report.claims,
            total_claims=len(report.claims),
            supported_claims=len(supported),
            conflicting_claims=len([c for c in report.claims if c.claim_id in conflicting_ids]),
            confidence_threshold=confidence_threshold,
            source_refs=[s.source_id for s in report.verified_sources],
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens of length 3+, ignoring punctuation."""
    cleaned = "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in text)
    return {w for w in cleaned.split() if len(w) >= 3}


_NEGATIONS = frozenset({"not", "never", "no", "cannot", "wont", "isnt", "doesnt", "didnt", "false"})
_AFFIRMATIONS = frozenset({"is", "are", "was", "were", "true", "yes", "can", "will"})


def _polarity(text: str) -> str:
    """Very coarse polarity signal.

    Only negation and affirmation tokens count. Anything else resolves to
    "neutral" so that two factual statements without either token are treated as
    agreeing rather than conflicting.
    """
    tokens = _tokens(text)
    has_negation = bool(tokens & _NEGATIONS)
    has_affirmation = bool(tokens & _AFFIRMATIONS)

    if has_negation and not has_affirmation:
        return "negative"
    if has_affirmation and not has_negation:
        return "positive"
    return "neutral"
