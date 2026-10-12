"""Tests for live model provider adapters (TASK-007).

Every adapter test runs against ``httpx.MockTransport``: the request is a real
HTTP POST through httpx, but the transport is injected and no network packet is
sent. This is the same offline-transport convention the research provider
tests use.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from lpf.errors import ConfigError, LpfError, ProviderError, ValidationError
from lpf.models import (
    HttpChatModel,
    OllamaModel,
    OpenAICompatibleModel,
    OpenCodeServerModel,
    create_live_model,
)
from lpf.models.provider import ModelProvider
from lpf.orchestration.model import protocol_satisfied
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.research.transport import RetryPolicy
from lpf.schemas.discovery import DiscoveryInputs

OPENAI_BASE = "https://api.openai.com/v1"
OLLAMA_BASE = "http://localhost:11434"


class LessonDraft(BaseModel):
    title: str
    body: str
    tags: list[str]


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json200(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={})


def _openai_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _ollama_payload(content: str) -> dict:
    return {"message": {"content": content}}


def _capture(seen: dict, handler) -> None:
    """Request body/headers/url recorder that continues to the real handler."""

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["payload"] = json.loads(request.content)
        return handler(request)

    return wrapped


# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------


class TestOpenAICompatibleModel:
    async def test_text_generation_hits_chat_completions(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openai_payload("hello world"))

        provider = OpenAICompatibleModel(
            api_key="secret", base_url=OPENAI_BASE, client=_client(_capture(seen, handler))
        )
        text = await provider.generate(
            messages=[{"role": "user", "content": "hi"}], temperature=0.0
        )
        assert text == "hello world"
        assert seen["url"] == "https://api.openai.com/v1/chat/completions"
        assert seen["payload"]["model"] == "gpt-4o-mini"
        assert seen["payload"]["messages"] == [{"role": "user", "content": "hi"}]
        assert seen["payload"]["temperature"] == 0.0
        assert seen["headers"]["authorization"] == "Bearer secret"
        assert "response_format" not in seen["payload"]

    async def test_no_bearer_when_api_key_is_none(self) -> None:
        seen: dict = {}
        provider = OpenAICompatibleModel(
            client=_client(_capture(seen, lambda r: httpx.Response(200, json=_openai_payload(""))))
        )
        await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert "authorization" not in seen["headers"]

    async def test_schema_requests_json_object_and_returns_model(self) -> None:
        seen: dict = {}
        draft = LessonDraft(title="Equations", body="An equality.", tags=["algebra"])

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openai_payload(draft.model_dump_json()))

        provider = OpenAICompatibleModel(
            api_key="secret", base_url=OPENAI_BASE, client=_client(_capture(seen, handler))
        )
        result = await provider.generate(
            messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
        )
        assert isinstance(result, LessonDraft)
        assert result.title == "Equations"
        assert result.tags == ["algebra"]
        assert seen["payload"]["response_format"] == {"type": "json_object"}

    async def test_malformed_json_raises_validation_error(self) -> None:
        provider = OpenAICompatibleModel(
            client=_client(lambda r: httpx.Response(200, json=_openai_payload("{not json")))
        )
        with pytest.raises(ValidationError) as excinfo:
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )
        assert excinfo.value.code == "MODEL_OUTPUT_NOT_JSON"
        assert isinstance(excinfo.value, LpfError)

    async def test_non_object_json_raises_validation_error(self) -> None:
        provider = OpenAICompatibleModel(
            client=_client(lambda r: httpx.Response(200, json=_openai_payload('"just a string"')))
        )
        with pytest.raises(ValidationError) as excinfo:
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )
        assert excinfo.value.code == "MODEL_OUTPUT_NOT_JSON"

    async def test_wrong_schema_raises_validation_error(self) -> None:
        provider = OpenAICompatibleModel(
            client=_client(lambda r: httpx.Response(200, json=_openai_payload('{"title": 42}')))
        )
        with pytest.raises(ValidationError) as excinfo:
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )
        assert excinfo.value.code == "MODEL_OUTPUT_INVALID_SCHEMA"
        assert "LessonDraft" in excinfo.value.message

    async def test_non_retryable_http_error_raises_provider_error(self) -> None:
        provider = OpenAICompatibleModel(client=_client(lambda r: httpx.Response(401)))
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "PROVIDER_HTTP_ERROR"

    async def test_transport_failure_raises_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "PROVIDER_REQUEST_FAILED"

    async def test_malformed_vendor_envelope_raises_provider_error(self) -> None:
        provider = OpenAICompatibleModel(
            client=_client(lambda r: httpx.Response(200, json={"unexpected": True}))
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "PROVIDER_RESPONSE_MALFORMED"

    async def test_effective_max_tokens_is_sent(self) -> None:
        seen: dict = {}
        provider = OpenAICompatibleModel(
            client=_client(_capture(seen, lambda r: httpx.Response(200, json=_openai_payload(""))))
        )
        await provider.generate(messages=[{"role": "user", "content": "hi"}], max_tokens=64)
        assert seen["payload"]["max_tokens"] == 64

    async def test_count_tokens(self) -> None:
        provider = OpenAICompatibleModel(client=_client(lambda r: httpx.Response(200)))
        assert await provider.count_tokens("a b c") == 3

    def test_defaults(self) -> None:
        provider = OpenAICompatibleModel(client=_client(lambda r: httpx.Response(200)))
        assert provider.model == "gpt-4o-mini"
        assert provider.base_url == "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class TestOllamaModel:
    async def test_text_generation_hits_native_chat(self) -> None:
        seen: dict = {}
        provider = OllamaModel(
            client=_client(
                _capture(seen, lambda r: httpx.Response(200, json=_ollama_payload("hello")))
            )
        )
        text = await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert text == "hello"
        assert seen["url"] == "http://localhost:11434/api/chat"
        assert seen["payload"]["model"] == "llama3.2"
        assert "authorization" not in seen["headers"]
        assert "format" not in seen["payload"]

    async def test_schema_requests_json_format(self) -> None:
        seen: dict = {}
        draft = LessonDraft(title="Equations", body="An equality.", tags=["algebra"])

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_ollama_payload(draft.model_dump_json()))

        provider = OllamaModel(client=_client(_capture(seen, handler)))
        result = await provider.generate(
            messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
        )
        assert isinstance(result, LessonDraft)
        assert result.body == "An equality."
        assert seen["payload"]["format"] == "json"

    async def test_malformed_json_raises_validation_error(self) -> None:
        provider = OllamaModel(
            client=_client(lambda r: httpx.Response(200, json=_ollama_payload("{} not json")))
        )
        with pytest.raises(ValidationError, match="MODEL_OUTPUT_NOT_JSON"):
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )

    async def test_malformed_vendor_envelope_raises_provider_error(self) -> None:
        provider = OllamaModel(client=_client(lambda r: httpx.Response(200, json={"done": True})))
        with pytest.raises(ProviderError, match="PROVIDER_RESPONSE_MALFORMED"):
            await provider.generate(messages=[{"role": "user", "content": "hi"}])

    def test_defaults(self) -> None:
        provider = OllamaModel(client=_client(lambda r: httpx.Response(200)))
        assert provider.model == "llama3.2"
        assert provider.base_url == "http://localhost:11434"


# ---------------------------------------------------------------------------
# Resilience: bounded retry, deterministic backoff (TASK-008)
# ---------------------------------------------------------------------------


class TestProviderResilience:
    def _flaky(
        self,
        *,
        failures: list[str],
    ):
        """Handler that raises ConnectError or returns a status per call."""
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            step = min(calls["count"], len(failures) - 1)
            calls["count"] += 1
            behaviour = failures[step]
            if behaviour == "connect":
                raise httpx.ConnectError("no route to host")
            if behaviour.isdigit():
                return httpx.Response(int(behaviour))
            return httpx.Response(200, json=_openai_payload(behaviour))

        return handler, calls

    async def test_retryable_status_then_success(self) -> None:
        handler, calls = self._flaky(failures=["503", "503", "ok"])
        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
        text = await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert text == "ok"
        assert calls["count"] == 3

    async def test_transport_failure_then_success(self) -> None:
        handler, calls = self._flaky(failures=["connect", "connect", "ok"])
        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
        text = await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert text == "ok"
        assert calls["count"] == 3

    async def test_retries_are_bounded(self) -> None:
        handler, calls = self._flaky(failures=["connect", "connect", "connect", "connect"])
        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=4, backoff_seconds=0.0),
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "PROVIDER_REQUEST_FAILED"
        assert calls["count"] == 4
        assert "4 attempt(s)" in excinfo.value.message
        assert excinfo.value.details["last_failure"].startswith("ConnectError")

    async def test_constant_retryable_status_failure_message(self) -> None:
        handler, calls = self._flaky(failures=["503", "503", "503"])
        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert "3 attempt(s)" in excinfo.value.message
        assert excinfo.value.details["last_failure"] == "HTTP 503"
        assert calls["count"] == 3

    async def test_non_retryable_status_is_not_retried(self) -> None:
        handler, calls = self._flaky(failures=["401", "401", "401"])
        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "PROVIDER_HTTP_ERROR"
        assert calls["count"] == 1

    async def test_backoff_delays_are_deterministic(self, monkeypatch) -> None:
        import lpf.models.providers.base as base

        recorded: list[float] = []
        real_sleep = base.asyncio.sleep

        async def fake_sleep(delay: float) -> None:
            recorded.append(delay)
            await real_sleep(0.0)

        monkeypatch.setattr(base.asyncio, "sleep", fake_sleep)
        handler, _ = self._flaky(failures=["connect", "connect", "ok"])
        provider = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=3, backoff_seconds=0.25, backoff_multiplier=2.0),
        )
        text = await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert text == "ok"
        assert recorded == [0.25, 0.5]


# ---------------------------------------------------------------------------
# Factory + protocol conformance
# ---------------------------------------------------------------------------


class TestCreateLiveModel:
    def test_builds_openai_compatible(self) -> None:
        provider = create_live_model("openai-compatible", api_key="k", client=_client(_json200))
        assert isinstance(provider, OpenAICompatibleModel)
        assert OpenAICompatibleModel.kind == "openai-compatible"

    def test_openai_kind_underscore_alias_resolves(self) -> None:
        provider = create_live_model("openai_compatible", api_key="k", client=_client(_json200))
        assert isinstance(provider, OpenAICompatibleModel)

    def test_builds_ollama(self) -> None:
        provider = create_live_model("ollama", client=_client(_json200))
        assert isinstance(provider, OllamaModel)

    @pytest.mark.parametrize("kind", ["ollama", "OLLAMA", " oLLaMa"])
    def test_kind_lookup_is_case_and_whitespace_insensitive(self, kind: str) -> None:
        provider = create_live_model(kind, client=_client(_json200))
        assert isinstance(provider, OllamaModel)

    @pytest.mark.parametrize("kind", ["openai-compatible", "openai_compatible", "ollama"])
    def test_cli_advertised_kinds_resolve_via_the_real_factory(self, kind: str) -> None:
        """The CLI passes ``kind.lower()`` straight to the factory, so every
        advertised ``--model`` / ``LPF_PROVIDER`` value must resolve there."""
        provider = create_live_model(kind, timeout_seconds=1, client=_client(_json200))
        assert isinstance(provider, HttpChatModel)

    def test_unknown_kind_raises_config_error(self) -> None:
        with pytest.raises(ConfigError) as excinfo:
            create_live_model("claude")
        assert excinfo.value.code == "UNKNOWN_MODEL_KIND"
        assert isinstance(excinfo.value, LpfError)


class TestAdapterContract:
    @pytest.mark.parametrize(
        "factory",
        [
            lambda: OpenAICompatibleModel(
                client=_client(lambda r: httpx.Response(200, json=_openai_payload("")))
            ),
            lambda: OllamaModel(
                client=_client(lambda r: httpx.Response(200, json=_ollama_payload("")))
            ),
        ],
    )
    def test_adapters_satisfy_model_provider_protocol(self, factory) -> None:
        provider = factory()
        assert isinstance(provider, ModelProvider)
        assert protocol_satisfied(provider)


# ---------------------------------------------------------------------------
# Pipeline: the seam is selectable per run; malformed output fails the run.
# ---------------------------------------------------------------------------


def _prose_handler(request: httpx.Request) -> httpx.Response:
    """Deterministic, claim-free prose / canonical worked-example draft.

    Text calls (lesson bodies) get prose; structured calls (worked examples,
    TASK-009) get the canonical, numerically-clean ``WorkedExampleDraft`` so the
    run passes QA and the package is reproducible.
    """
    body = json.loads(request.content)
    structured = bool(body.get("response_format") or body.get("format"))
    user = next(
        message["content"]
        for message in reversed(body["messages"])
        if message.get("role") == "user"
    )
    if not structured:
        title = user.replace("Explain ", "").split(" for a")[0]
        content = (
            f"{title} is defined by a clear rule that links the idea to its use. "
            "The key idea is introduced in plain language and applied in one example. "
            "The common mistake is treating the rule as a formula to memorise."
        )
        return httpx.Response(200, json=_openai_payload(content))

    start, end = user.find('"'), user.rfind('"')
    title = user[start + 1 : end] if start != -1 and end > start else "the topic"
    draft = {
        "problem_statement": f"Apply what you just learned: {title}.",
        "solution_steps": [
            {"order": 1, "statement": "Identify what is being asked."},
            {"order": 2, "statement": "Choose the method that fits."},
            {
                "order": 3,
                "statement": "Carry it out and check the result.",
                "expression": "result = apply(method, problem)",
            },
        ],
        "final_answer": "The problem is solved and the result checked.",
        "common_errors": ["Skips the check step."],
    }
    return httpx.Response(200, json=_openai_payload(json.dumps(draft)))


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="I am a year 10 student and I keep failing at linear algebra.",
        subject="linear algebra",
        level="year 10",
    )


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class TestLiveModelInPipeline:
    async def test_live_model_runs_the_full_pipeline(self, tmp_path: Path) -> None:
        model = OpenAICompatibleModel(api_key="secret", client=_client(_prose_handler))
        pipeline = FactoryPipeline(output_dir=str(tmp_path / "a"), model=model)
        result = await pipeline.run(_inputs(), run_id="live")
        assert result.succeeded
        assert result.verification is not None
        assert result.package is not None

    async def test_live_model_output_is_reproducible(self, tmp_path: Path) -> None:
        model = OpenAICompatibleModel(api_key="secret", client=_client(_prose_handler))
        first = await FactoryPipeline(output_dir=str(tmp_path / "a"), model=model).run(
            _inputs(), run_id="live"
        )
        second = await FactoryPipeline(output_dir=str(tmp_path / "b"), model=model).run(
            _inputs(), run_id="live"
        )
        assert first.package is not None and second.package is not None
        assert _tree_hash(first.package.root) == _tree_hash(second.package.root)

    async def test_offline_default_is_still_deterministic_mock(self) -> None:
        from lpf.orchestration.model import DeterministicMockModel

        pipeline = FactoryPipeline(output_dir="projects")
        assert isinstance(pipeline._model, DeterministicMockModel)


class TestMalformedOutputFailsRun:
    class _MalformedStructuredModel:
        """Playback of the adapter's malformed-structured-output behaviour.

        `test_malformed_json_raises_validation_error` proves the real adapter
        raises this exact error; this test proves the pipeline turns that typed
        error into a FAILED run before QA ever runs.
        """

        async def generate(self, **kwargs) -> str:
            raise ValidationError(
                code="MODEL_OUTPUT_NOT_JSON",
                message="Model returned content that is not valid JSON.",
                details={"content_preview": "{not json"},
            )

        async def count_tokens(self, text: str) -> int:
            return len(text.split())

    async def test_run_fails_before_qa(self, tmp_path: Path) -> None:
        from lpf.orchestration.events import EventType
        from lpf.orchestration.state import RunStage

        model = self._MalformedStructuredModel()
        pipeline = FactoryPipeline(output_dir=str(tmp_path), model=model)
        result = await pipeline.run(_inputs(), run_id="malformed")
        assert not result.succeeded
        assert "MODEL_OUTPUT_NOT_JSON" in result.state.failure_reason
        assert result.verification is None
        visited = {transition.to_stage for transition in result.state.history}
        assert RunStage.CONTENT in visited
        assert RunStage.QA not in visited
        assert EventType.RUN_FAILED in {event.event_type for event in result.events.events}


class TestProviderDownFailsRun:
    async def test_constant_provider_failure_is_readable_and_deterministic(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        model = OpenAICompatibleModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
        pipeline = FactoryPipeline(output_dir=str(tmp_path), model=model)
        result = await pipeline.run(_inputs(), run_id="provider-down")
        assert not result.succeeded
        assert result.verification is None
        assert "PROVIDER_REQUEST_FAILED" in result.state.failure_reason
        assert "3 attempt(s)" in result.state.failure_reason


class TestClientLifecycle:
    """Live clients must be released, but an injected one must survive (TASK-014)."""

    async def test_model_closes_an_owned_client(self) -> None:
        model = OpenAICompatibleModel(api_key="k")
        assert model._owns_client is True
        await model.aclose()
        assert model._client.is_closed

    async def test_model_leaves_an_injected_client_open(self) -> None:
        client = _client(_json200)
        model = OpenAICompatibleModel(client=client)
        assert model._owns_client is False
        await model.aclose()
        assert not client.is_closed
        await client.aclose()

    async def test_pipeline_aclose_closes_owned_model_and_ignores_mock(
        self, tmp_path: Path
    ) -> None:
        model = OpenAICompatibleModel(api_key="k")
        pipeline = FactoryPipeline(output_dir=str(tmp_path), model=model)
        assert not model._client.is_closed
        await pipeline.aclose()
        assert model._client.is_closed

    async def test_pipeline_aclose_is_a_noop_for_the_offline_default(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        await pipeline.aclose()

    async def test_pipeline_aclose_closes_owned_research_providers(self, tmp_path: Path) -> None:
        from lpf.research.providers.arxiv import ArxivProvider
        from lpf.schemas.research import SearchProvider

        provider = ArxivProvider()
        pipeline = FactoryPipeline(
            output_dir=str(tmp_path),
            research_providers={SearchProvider.ARXIV: provider},
        )
        await pipeline.aclose()
        assert provider._transport.client.is_closed

    async def test_pipeline_aclose_after_a_run(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        await pipeline.run(_inputs(), run_id="close-after-run")
        await pipeline.aclose()


# ---------------------------------------------------------------------------
# OpenCode Server
# ---------------------------------------------------------------------------


def _opencode_session_response(session_id: str) -> dict:
    return {
        "id": session_id,
        "slug": "test-session",
        "projectID": "test-project",
        "directory": "/test",
        "path": "",
        "cost": 0,
        "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
        "title": "Test session",
        "version": "1.19.0",
        "time": {"created": 1234567890, "updated": 1234567890},
    }


def _opencode_message_response(text: str, model_id: str = "big-pickle") -> dict:
    return {
        "info": {
            "parentID": "msg_parent",
            "role": "assistant",
            "mode": "build",
            "agent": "build",
            "path": {"cwd": "/test", "root": "/test"},
            "cost": 0,
            "tokens": {"total": 100, "input": 80, "output": 10, "reasoning": 10, "cache": {"write": 0, "read": 0}},
            "modelID": model_id,
            "providerID": "opencode",
            "time": {"created": 1234567890, "completed": 1234567890},
            "finish": "stop",
            "id": "msg_123",
            "sessionID": "ses_test",
        },
        "parts": [
            {"type": "step-start", "id": "prt_1", "sessionID": "ses_test", "messageID": "msg_123"},
            {"type": "text", "text": text, "time": {"start": 1234567890, "end": 1234567890}, "id": "prt_2", "sessionID": "ses_test", "messageID": "msg_123"},
            {"type": "step-finish", "reason": "stop", "tokens": {"total": 100, "input": 80, "output": 10, "reasoning": 10, "cache": {"write": 0, "read": 0}}, "cost": 0, "id": "prt_3", "sessionID": "ses_test", "messageID": "msg_123"},
        ],
    }


class TestOpenCodeServerModel:
    async def test_text_generation_creates_session_and_sends_message(self) -> None:
        session_id = "ses_test123"
        seen: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["payload"] = json.loads(request.content)
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(200, json=_opencode_message_response("hello world"))

        provider = OpenCodeServerModel(
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        text = await provider.generate(messages=[{"role": "user", "content": "hi"}], temperature=0.0)
        assert text == "hello world"
        assert "ses_test123" in seen["url"] or "session" in seen["url"]
        # First call creates session
        assert len([k for k in seen if k == "url"]) >= 1

    async def test_text_generation_reuses_session(self) -> None:
        session_id = "ses_reuse"
        call_count = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(200, json=_opencode_message_response("hi"))

        provider = OpenCodeServerModel(
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        await provider.generate(messages=[{"role": "user", "content": "hi"}])
        await provider.generate(messages=[{"role": "user", "content": "hi again"}])
        # Session created once, then reused
        assert call_count["n"] == 3  # 1 session create + 2 messages

    async def test_schema_requests_json_and_returns_model(self) -> None:
        session_id = "ses_schema"
        draft = LessonDraft(title="Equations", body="An equality.", tags=["algebra"])

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            # The structured prompt includes the system prompt + user message
            return httpx.Response(200, json=_opencode_message_response(draft.model_dump_json()))

        provider = OpenCodeServerModel(
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        result = await provider.generate(
            messages=[{"role": "user", "content": "Generate a lesson"}],
            schema=LessonDraft,
        )
        assert isinstance(result, LessonDraft)
        assert result.title == "Equations"
        assert result.tags == ["algebra"]

    async def test_malformed_json_raises_validation_error(self) -> None:
        session_id = "ses_badjson"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(200, json=_opencode_message_response("{not json"))

        provider = OpenCodeServerModel(
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        with pytest.raises(ValidationError) as excinfo:
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )
        assert excinfo.value.code == "MODEL_OUTPUT_NOT_JSON"

    async def test_non_object_json_raises_validation_error(self) -> None:
        session_id = "ses_nonobj"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(200, json=_opencode_message_response('"just a string"'))

        provider = OpenCodeServerModel(
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        with pytest.raises(ValidationError) as excinfo:
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )
        assert excinfo.value.code == "MODEL_OUTPUT_NOT_JSON"

    async def test_wrong_schema_raises_validation_error(self) -> None:
        session_id = "ses_wrongschema"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(200, json=_opencode_message_response('{"title": 42}'))

        provider = OpenCodeServerModel(
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        with pytest.raises(ValidationError) as excinfo:
            await provider.generate(
                messages=[{"role": "user", "content": "hi"}], schema=LessonDraft
            )
        assert excinfo.value.code == "MODEL_OUTPUT_INVALID_SCHEMA"
        assert "LessonDraft" in excinfo.value.message

    async def test_non_retryable_http_error_raises_provider_error(self) -> None:
        session_id = "ses_401"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(401)

        provider = OpenCodeServerModel(
            client=_client(handler), base_url="http://127.0.0.1:4120"
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "OPENCODE_MESSAGE_FAILED"

    async def test_transport_failure_raises_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        provider = OpenCodeServerModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
            base_url="http://127.0.0.1:4120",
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        # Session creation happens first, so transport failure hits that endpoint
        assert excinfo.value.code == "OPENCODE_SESSION_CREATE_FAILED"

    async def test_malformed_response_raises_provider_error(self) -> None:
        session_id = "ses_malformed"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            return httpx.Response(200, json={"parts": []})  # no text part

        provider = OpenCodeServerModel(
            client=_client(handler), base_url="http://127.0.0.1:4120"
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "OPENCODE_RESPONSE_MALFORMED"

    async def test_session_create_failure_raises_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        provider = OpenCodeServerModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
            base_url="http://127.0.0.1:4120",
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "OPENCODE_SESSION_CREATE_FAILED"

    async def test_session_missing_id_raises_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"slug": "test"})  # missing 'id'

        provider = OpenCodeServerModel(
            client=_client(handler),
            retry=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
            base_url="http://127.0.0.1:4120",
        )
        with pytest.raises(ProviderError) as excinfo:
            await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert excinfo.value.code == "OPENCODE_SESSION_MISSING_ID"

    async def test_model_parameter_overrides_default(self) -> None:
        session_id = "ses_modelparam"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=_opencode_message_response("ok", model_id="big-pickle"))

        seen: dict = {}
        provider = OpenCodeServerModel(
            model="big-pickle",
            base_url="http://127.0.0.1:4120",
            client=_client(handler),
        )
        await provider.generate(messages=[{"role": "user", "content": "hi"}], model="nemotron-3-ultra-free")
        assert seen["payload"].get("model") == {"providerID": "opencode", "modelID": "nemotron-3-ultra-free"}

    async def test_count_tokens(self) -> None:
        provider = OpenCodeServerModel(client=_client(lambda r: httpx.Response(200)))
        assert await provider.count_tokens("a b c") == 3

    def test_defaults(self) -> None:
        provider = OpenCodeServerModel(client=_client(lambda r: httpx.Response(200)))
        assert provider.model == "big-pickle"
        assert provider.base_url == "http://127.0.0.1:4120"
        assert provider.provider_id == "opencode"

    async def test_aclose_deletes_session(self) -> None:
        session_id = "ses_close"
        delete_called = {"called": False}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            if request.url.path == f"/session/{session_id}" and request.method == "DELETE":
                delete_called["called"] = True
                return httpx.Response(200)
            return httpx.Response(200, json=_opencode_message_response("ok"))

        provider = OpenCodeServerModel(base_url="http://127.0.0.1:4120")
        # Inject mock client after creation so provider owns it
        provider._client = _client(handler)
        provider._owns_client = True
        await provider.generate(messages=[{"role": "user", "content": "hi"}])
        await provider.aclose()
        assert delete_called["called"] is True

    async def test_aclose_does_not_delete_unowned_client(self) -> None:
        session_id = "ses_no_delete"
        delete_called = {"called": False}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=_opencode_session_response(session_id))
            if request.url.path == f"/session/{session_id}" and request.method == "DELETE":
                delete_called["called"] = True
                return httpx.Response(200)
            return httpx.Response(200, json=_opencode_message_response("ok"))

        client = _client(handler)
        provider = OpenCodeServerModel(base_url="http://127.0.0.1:4120", client=client)
        await provider.generate(messages=[{"role": "user", "content": "hi"}])
        await provider.aclose()
        # Injected client -> we don't delete the session
        assert delete_called["called"] is False
        await client.aclose()


# ---------------------------------------------------------------------------
# CreateLiveModel: opencode-server
# ---------------------------------------------------------------------------


class TestCreateLiveModelOpenCode:
    def test_builds_opencode_server(self) -> None:
        provider = create_live_model("opencode-server", client=_client(_json200))
        assert isinstance(provider, OpenCodeServerModel)
        assert OpenCodeServerModel.kind == "opencode-server"

    def test_kind_alias_resolves(self) -> None:
        provider = create_live_model("opencode_server", client=_client(_json200))
        assert isinstance(provider, OpenCodeServerModel)

    @pytest.mark.parametrize("kind", ["opencode-server", "opencode_server", "OPENCODE-SERVER"])
    def test_kind_lookup_case_insensitive(self, kind: str) -> None:
        provider = create_live_model(kind, client=_client(_json200))
        assert isinstance(provider, OpenCodeServerModel)
