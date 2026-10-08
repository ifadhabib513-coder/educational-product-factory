"""Deterministic Markdown → standalone HTML rendering for packaged products.

``product.md`` is the canonical product document; this module converts it to
a single self-contained HTML file that opens with no server, no build step
and no external assets.

Only the constructs the factory actually emits are supported — headings,
paragraphs, bullet and ordered lists, pipe tables, ``**bold**``, ``*italic*``
and ```code``` — so the converter stays small, auditable and exactly
deterministic. Text is HTML-escaped before any markup is applied, so a lesson
containing ``<script>`` ships as visible text, never as live markup.
"""

from __future__ import annotations

import html
import re
from typing import Final

__all__ = [
    "markdown_to_html",
    "render_html_document",
]

_HEADING_RE: Final = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED_RE: Final = re.compile(r"^\s*\d+\.\s+(.*)$")
_UNORDERED_RE: Final = re.compile(r"^\s*[-*]\s+(.*)$")
_INLINE_CODE_RE: Final = re.compile(r"`([^`]+)`")
_BOLD_RE: Final = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE: Final = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")

#: Placeholder used to park rendered code spans while emphasis is applied.
_CODE_PLACEHOLDER: Final = "\x00{index}\x00"

_STYLE: Final = """\
:root {
  color-scheme: light dark;
  --fg: #1a1a1a;
  --muted: #5c5c5c;
  --rule: #d9d9d9;
  --accent: #0b5fff;
  --code-bg: #f2f2f2;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fg: #e8e8e8;
    --muted: #a0a0a0;
    --rule: #333333;
    --accent: #7aa2ff;
    --code-bg: #262626;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2rem 1rem 4rem;
  background: Canvas;
  color: var(--fg);
  font: 16px/1.65 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.product {
  max-width: 46rem;
  margin: 0 auto;
}
h1, h2, h3, h4, h5, h6 { line-height: 1.25; margin: 2rem 0 0.75rem; }
h1 { font-size: 1.9rem; margin-top: 0; }
h2 { font-size: 1.4rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.3rem; }
p { margin: 0 0 1rem; }
ul, ol { margin: 0 0 1rem; padding-left: 1.4rem; }
li { margin-bottom: 0.3rem; }
code {
  background: var(--code-bg);
  border-radius: 3px;
  padding: 0.1em 0.35em;
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 0.92em;
}
table { border-collapse: collapse; width: 100%; margin: 0 0 1.5rem; }
th, td { border: 1px solid var(--rule); padding: 0.45rem 0.6rem; text-align: left; }
th { background: var(--code-bg); font-weight: 600; }
"""


def _inline(text: str) -> str:
    """Escape ``text`` and apply inline emphasis and code spans."""
    escaped = html.escape(text, quote=False)

    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(f"<code>{match.group(1)}</code>")
        return _CODE_PLACEHOLDER.format(index=len(spans) - 1)

    without_code = _INLINE_CODE_RE.sub(stash, escaped)
    without_code = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", without_code)
    without_code = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", without_code)

    for index, span in enumerate(spans):
        without_code = without_code.replace(_CODE_PLACEHOLDER.format(index=index), span)
    return without_code


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "-" not in stripped:
        return False
    return all(character in "|-: \t" for character in stripped)


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in headers)
    body = ["<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in rows]
    return "\n".join(
        [
            "<table>",
            "<thead>",
            f"<tr>{head}</tr>",
            "</thead>",
            "<tbody>",
            *body,
            "</tbody>",
            "</table>",
        ]
    )


def markdown_to_html(markdown: str) -> str:
    """Convert the factory's Markdown subset into an HTML fragment."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    open_list: str | None = None
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal open_list
        if open_list is not None:
            blocks.append(f"</{open_list}>")
            open_list = None

    def start_list(tag: str) -> None:
        nonlocal open_list
        if open_list != tag:
            close_list()
            blocks.append(f"<{tag}>")
            open_list = tag

    while index < len(lines):
        line = lines[index]

        if (
            line.lstrip().startswith("|")
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            flush_paragraph()
            close_list()
            headers = _split_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append(_split_row(lines[index]))
                index += 1
            blocks.append(_render_table(headers, rows))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
            index += 1
            continue

        unordered = _UNORDERED_RE.match(line)
        if unordered:
            flush_paragraph()
            start_list("ul")
            blocks.append(f"<li>{_inline(unordered.group(1))}</li>")
            index += 1
            continue

        ordered = _ORDERED_RE.match(line)
        if ordered:
            flush_paragraph()
            start_list("ol")
            blocks.append(f"<li>{_inline(ordered.group(1))}</li>")
            index += 1
            continue

        paragraph.append(line.strip())
        index += 1

    flush_paragraph()
    close_list()
    return "\n".join(blocks)


def render_html_document(markdown: str, *, title: str) -> str:
    """Render ``markdown`` as a self-contained standalone HTML document."""
    body = markdown_to_html(markdown)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "<style>\n"
        f"{_STYLE}"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        '<main class="product">\n'
        f"{body}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
