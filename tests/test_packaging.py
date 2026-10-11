"""Tests for multi-format packaging (TASK-005).

Covers the Markdown→HTML converter, the archival ZIP bundler, and the wiring
that makes both land in every run's output directory.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from lpf.domain.identity import with_content_hash
from lpf.domain.quality import GateStatus, QualityGate, VerificationResult
from lpf.orchestration.context import RunContext
from lpf.orchestration.events import EventLog
from lpf.orchestration.packaging_stage import package_run
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.orchestration.state import RunStage, RunState
from lpf.packaging import build_run_bundle, markdown_to_html, render_html_document
from lpf.schemas.discovery import DiscoveryInputs


def _normalize(text: str) -> str:
    """Collapse whitespace so structural assertions read as markup, not layout."""
    return " ".join(text.split())


def _markup(text: str) -> str:
    """Like ``_normalize``, but also drop the gap between adjacent tags."""
    return _normalize(text).replace("> <", "><")


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="Teach me linear algebra basics.",
        subject="linear algebra",
        level="year 10",
    )


async def _run(tmp_path: Path, *, run_id: str = "pkg-run"):
    pipeline = FactoryPipeline(output_dir=str(tmp_path))
    return await pipeline.run(_inputs(), run_id=run_id, seed="s")


_SAMPLE_MARKDOWN = """\
# Product title

**Level:** year 10

## The problem this solves

A paragraph with `inline code` and **bold** text.

## Lessons

### Lesson one

Another paragraph.

## What you will be able to do

- First objective
- Second objective

## Practice

1. First question
2. Second question

## Quality

| Gate | Status |
| --- | --- |
| factual_consistency | passed |
| numerical_consistency | failed |
"""


# ---------------------------------------------------------------------------
# Markdown fragment conversion
# ---------------------------------------------------------------------------


class TestMarkdownToHtml:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("# Title", "<h1>Title</h1>"),
            ("## Section", "<h2>Section</h2>"),
            ("### Lesson", "<h3>Lesson</h3>"),
            ("###### Deep", "<h6>Deep</h6>"),
        ],
    )
    def test_headings(self, source: str, expected: str) -> None:
        assert _markup(markdown_to_html(source)) == expected

    def test_paragraphs_are_wrapped(self) -> None:
        html = markdown_to_html("First sentence.\n\nSecond sentence.")
        assert _markup(html) == "<p>First sentence.</p><p>Second sentence.</p>"

    def test_bullet_list(self) -> None:
        html = markdown_to_html("- alpha\n- beta")
        assert _markup(html) == "<ul><li>alpha</li><li>beta</li></ul>"

    def test_ordered_list(self) -> None:
        html = markdown_to_html("1. alpha\n2. beta")
        assert _markup(html) == "<ol><li>alpha</li><li>beta</li></ol>"

    def test_pipe_table(self) -> None:
        html = markdown_to_html(_SAMPLE_MARKDOWN)
        assert "<table>" in html
        assert "<thead>" in html
        assert _normalize(html).count("<th>") == 2
        assert "<td>factual_consistency</td><td>passed</td>" in _normalize(html)

    def test_inline_emphasis(self) -> None:
        html = markdown_to_html("A **bold** and *italic* and `code` span.")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html
        assert "<code>code</code>" in html

    def test_markup_inside_code_is_not_reinterpreted(self) -> None:
        html = markdown_to_html("Use `a ** b` and `* c` here.")
        assert "<code>a ** b</code>" in html
        assert "<code>* c</code>" in html
        assert "<strong>" not in html

    @pytest.mark.parametrize(
        "dangerous",
        [
            "<script>alert(1)</script>",
            'An <img src="x" onerror="y"> tag',
            "a & b",
        ],
    )
    def test_raw_markup_is_escaped_never_emitted(self, dangerous: str) -> None:
        html = markdown_to_html(dangerous)
        assert "<script" not in html
        assert "<img" not in html
        assert "&amp;" in html or "&lt;" in html

    def test_carriage_returns_are_normalised(self) -> None:
        assert markdown_to_html("# Title\r\n\r\nBody") == markdown_to_html("# Title\n\nBody")

    def test_empty_input_produces_an_empty_fragment(self) -> None:
        assert markdown_to_html("") == ""

    def test_conversion_is_deterministic(self) -> None:
        assert markdown_to_html(_SAMPLE_MARKDOWN) == markdown_to_html(_SAMPLE_MARKDOWN)


# ---------------------------------------------------------------------------
# Standalone document
# ---------------------------------------------------------------------------


class TestStandaloneDocument:
    def test_is_a_complete_html_document(self) -> None:
        document = render_html_document(_SAMPLE_MARKDOWN, title="My Product")
        assert document.startswith("<!DOCTYPE html>")
        assert document.endswith("</html>\n")
        assert '<meta charset="utf-8">' in document
        assert "<title>My Product</title>" in document
        assert '<main class="product">' in document

    def test_body_contains_the_converted_content(self) -> None:
        document = render_html_document(_SAMPLE_MARKDOWN, title="T")
        assert "<h1>Product title</h1>" in document
        assert "<td>numerical_consistency</td><td>failed</td>" in _normalize(document)

    def test_title_is_escaped(self) -> None:
        document = render_html_document("", title="A <b>title</b>")
        assert "<title>A &lt;b&gt;title&lt;/b&gt;</title>" in document
        assert "<title>A <b>title</b></title>" not in document

    def test_empty_markdown_still_yields_a_document(self) -> None:
        document = render_html_document("", title="Empty")
        assert document.startswith("<!DOCTYPE html>")
        assert document.endswith("</html>\n")

    def test_rendering_is_deterministic(self) -> None:
        assert render_html_document(_SAMPLE_MARKDOWN, title="T") == render_html_document(
            _SAMPLE_MARKDOWN, title="T"
        )


# ---------------------------------------------------------------------------
# ZIP bundle
# ---------------------------------------------------------------------------


class TestRunBundle:
    @staticmethod
    def _make_files(directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        payloads = {
            "manifest.json": '{"run_id": "b"}',
            "product.md": "# Title",
            "product.html": "<!DOCTYPE html>",
            "artifacts/lesson__a.json": '{"id": "a"}',
        }
        paths: dict[str, Path] = {}
        for name, text in payloads.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            paths[name] = path
        return paths

    def test_writes_a_zip_named_after_the_run(self, tmp_path: Path) -> None:
        files = self._make_files(tmp_path / "src")
        bundle = build_run_bundle(root=tmp_path, run_id="b", members=files.items())
        assert bundle == tmp_path / "b.zip"
        assert bundle.is_file()

    def test_contains_manifest_markdown_html_and_json_artifacts(self, tmp_path: Path) -> None:
        files = self._make_files(tmp_path / "src")
        bundle = build_run_bundle(root=tmp_path, run_id="b", members=files.items())
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        assert names == {
            "manifest.json",
            "product.md",
            "product.html",
            "artifacts/lesson__a.json",
        }

    def test_members_round_trip_byte_for_byte(self, tmp_path: Path) -> None:
        files = self._make_files(tmp_path / "src")
        bundle = build_run_bundle(root=tmp_path, run_id="b", members=files.items())
        with zipfile.ZipFile(bundle) as archive:
            for name, path in files.items():
                assert archive.read(name) == path.read_bytes()

    def test_member_order_is_sorted_not_insertion_order(self, tmp_path: Path) -> None:
        files = self._make_files(tmp_path / "src")
        shuffled = dict(reversed(list(files.items())))
        bundle = build_run_bundle(root=tmp_path, run_id="b", members=shuffled.items())
        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()
        assert names == sorted(names)

    def test_two_builds_from_the_same_inputs_are_byte_identical(self, tmp_path: Path) -> None:
        left = self._make_files(tmp_path / "left")
        right = self._make_files(tmp_path / "right")
        (tmp_path / "o1").mkdir()
        (tmp_path / "o2").mkdir()
        first = build_run_bundle(root=tmp_path / "o1", run_id="b", members=left.items())
        second = build_run_bundle(root=tmp_path / "o2", run_id="b", members=right.items())
        assert first.read_bytes() == second.read_bytes()

    def test_per_entry_metadata_is_pinned(self, tmp_path: Path) -> None:
        """The determinism rests on asserted invariants, not a same-host rerun.

        Each entry must carry the fixed DOS epoch, ``create_system`` Unix, the
        fixed Unix mode, and deflate compression -- the fields that would
        otherwise vary with the building host and break byte-identity.
        """
        files = self._make_files(tmp_path / "src")
        bundle = build_run_bundle(root=tmp_path, run_id="b", members=files.items())
        with zipfile.ZipFile(bundle) as archive:
            assert len(archive.infolist()) == len(files)
            for info in archive.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0)
                assert info.create_system == 3
                assert info.external_attr == 0o644 << 16
                assert info.compress_type == zipfile.ZIP_DEFLATED

    def test_entries_carry_a_fixed_timestamp(self, tmp_path: Path) -> None:
        files = self._make_files(tmp_path / "src")
        bundle = build_run_bundle(root=tmp_path, run_id="b", members=files.items())
        with zipfile.ZipFile(bundle) as archive:
            stamps = {info.date_time for info in archive.infolist()}
        assert stamps == {(1980, 1, 1, 0, 0, 0)}

    def test_the_bundle_never_packages_itself(self, tmp_path: Path) -> None:
        files = self._make_files(tmp_path / "src")
        build_run_bundle(root=tmp_path, run_id="b", members=files.items())
        with zipfile.ZipFile(tmp_path / "b.zip") as archive:
            assert "b.zip" not in archive.namelist()


# ---------------------------------------------------------------------------
# The packaging stage produces all formats
# ---------------------------------------------------------------------------


class TestPackagingStageOutputs:
    async def test_run_writes_html_and_zip_beside_the_markdown(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        assert result.succeeded
        package = result.package
        assert package is not None

        assert package.product_html_path == package.root / "product.html"
        assert package.product_html_path.is_file()
        assert package.bundle_path == package.root / f"{result.run_id}.zip"
        assert package.bundle_path.is_file()

        html = package.product_html_path.read_text(encoding="utf-8")
        assert html.startswith("<!DOCTYPE html>")
        assert "<title>" in html

    async def test_every_markdown_heading_survives_the_conversion(self, tmp_path: Path) -> None:
        result = await _run(tmp_path)
        package = result.package
        assert package is not None
        markdown = package.product_path.read_text(encoding="utf-8")
        html = package.product_html_path.read_text(encoding="utf-8")

        heading_levels = [
            len(line) - len(line.lstrip("#"))
            for line in markdown.splitlines()
            if line.startswith("#")
        ]
        assert heading_levels, "expected the product document to have headings"
        for level in heading_levels:
            assert f"<h{level}>" in html

    async def test_bundle_holds_the_manifest_markdown_html_and_artifacts(
        self, tmp_path: Path
    ) -> None:
        result = await _run(tmp_path, run_id="bundled")
        package = result.package
        assert package is not None

        with zipfile.ZipFile(package.bundle_path) as archive:
            names = set(archive.namelist())
            assert archive.testzip() is None

        assert {"manifest.json", "product.md", "product.html", "run_log.json"} <= names
        artifact_names = {name for name in names if name.startswith("artifacts/")}
        assert artifact_names == {f"artifacts/{path.name}" for path in package.artifact_paths}
        assert len(artifact_names) == len(result.artifacts)

        with zipfile.ZipFile(package.bundle_path) as archive:
            assert archive.read("product.md") == package.product_path.read_bytes()
            assert archive.read("product.html") == package.product_html_path.read_bytes()

    async def test_two_runs_produce_byte_identical_bundles(self, tmp_path: Path) -> None:
        first = await _run(tmp_path / "a", run_id="same")
        second = await _run(tmp_path / "b", run_id="same")
        assert first.package is not None
        assert second.package is not None
        assert first.package.bundle_path.read_bytes() == second.package.bundle_path.read_bytes()

    async def test_runs_without_any_artifacts_still_package(self, tmp_path: Path) -> None:
        """A bundle must not assume the artifact directory is non-empty."""
        root = tmp_path / "empty"

        ctx = RunContext(run_id="empty", seed="s", output_dir=str(root))
        verification = with_content_hash(
            VerificationResult(
                id="ver_1",
                created_at=ctx.now(),
                gates=[
                    with_content_hash(
                        QualityGate(
                            id="gate_1",
                            created_at=ctx.now(),
                            checked_at=ctx.now(),
                            gate_name="schema_validity",
                            status=GateStatus.PASSED,
                            score=1.0,
                        )
                    )
                ],
                overall_status=GateStatus.PASSED,
                overall_score=1.0,
            )
        )
        package = package_run(
            ctx,
            state=RunState(run_id="empty", stage=RunStage.COMPLETE),
            events=EventLog(run_id="empty"),
            artifacts=[],
            verification=verification,
        )

        assert package.bundle_path.is_file()
        with zipfile.ZipFile(package.bundle_path) as archive:
            names = set(archive.namelist())
        assert names == {"manifest.json", "product.md", "product.html", "run_log.json"}
        manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
        assert manifest["artifact_count"] == 0
