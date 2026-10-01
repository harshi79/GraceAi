"""A small, dependency-free Markdown engine.

Grace answers arrive incrementally, so the parser has to cope with *partial*
documents: an unterminated code fence must render as a code block containing
whatever has arrived so far, and an unclosed ``**`` must not swallow the rest
of the paragraph.

The output is a flat list of blocks plus inline spans.  The Tk renderer turns
those into ``Text`` widget inserts and tags; nothing in here touches the GUI.

Deliberately **not** implemented (and reported as such in the README):
Mermaid diagrams and real LaTeX typesetting.  Both are surfaced as labelled
source blocks instead of being silently dropped, because Grace's output format
for them could not be verified against the live API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Inline spans
# --------------------------------------------------------------------------- #

PLAIN = "plain"
BOLD = "bold"
ITALIC = "italic"
BOLD_ITALIC = "bold_italic"
CODE = "code"
LINK = "link"
STRIKE = "strike"
MATH = "math"


@dataclass
class Span:
    text: str
    style: str = PLAIN
    href: str = ""


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #


@dataclass
class Block:
    """Base class for every renderable block."""


@dataclass
class Paragraph(Block):
    spans: List[Span] = field(default_factory=list)


@dataclass
class Heading(Block):
    level: int
    spans: List[Span] = field(default_factory=list)


@dataclass
class CodeBlock(Block):
    code: str
    language: str = ""
    #: True while the closing fence has not arrived yet.
    open: bool = False


@dataclass
class ListItem(Block):
    spans: List[Span] = field(default_factory=list)
    ordered: bool = False
    number: int = 0
    depth: int = 0


@dataclass
class Quote(Block):
    spans: List[Span] = field(default_factory=list)


@dataclass
class Rule(Block):
    pass


@dataclass
class MathBlock(Block):
    source: str
    display: bool = True


@dataclass
class Table(Block):
    header: List[List[Span]] = field(default_factory=list)
    rows: List[List[List[Span]]] = field(default_factory=list)


@dataclass
class Spacer(Block):
    pass


# --------------------------------------------------------------------------- #
# Regexes
# --------------------------------------------------------------------------- #

_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([A-Za-z0-9_+.#-]*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_BULLET = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_ORDERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")
_MATH_DISPLAY = re.compile(r"^\s*\$\$(.*?)\$\*\s*$")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_BARE_URL = re.compile(r"(?<![\(\<])(https?://[^\s<>\)]+)")
_INLINE_CODE = re.compile(r"(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)")
_BOLD_ITALIC = re.compile(r"(\*\*\*|___)(?=\S)([\s\S]*?\S)\1")
_BOLD = re.compile(r"(\*\*|__)(?=\S)([\s\S]*?\S)\1")
_ITALIC = re.compile(r"(\*|_)(?=\S)([\s\S]*?\S)\1(?!\1)")
_STRIKE = re.compile(r"~~(?=\S)([\s\S]*?\S)~~")


# --------------------------------------------------------------------------- #
# Inline parsing
# --------------------------------------------------------------------------- #


def parse_inline(text: str) -> List[Span]:
    """Tokenise one line of inline markdown."""
    spans: List[Span] = []
    pos = 0
    length = len(text)

    def push(chunk: str, style: str = PLAIN, href: str = "") -> None:
        if chunk:
            spans.append(Span(chunk, style, href))

    while pos < length:
        # Inline code first: its contents are never re-parsed.
        match = _INLINE_CODE.search(text, pos)
        if match is None:
            _push_inline_tail(text[pos:], spans, push)
            break
        if match.start() > pos:
            _push_inline_tail(text[pos:match.start()], spans, push)
        push(match.group(2), CODE)
        pos = match.end()

    return _merge(spans)


def _push_inline_tail(chunk: str, spans: List[Span], push) -> None:
    """Handle emphasis / links inside a run of non-code text."""
    if not chunk:
        return
    remaining = chunk
    while remaining:
        best = _earliest(remaining)
        if best is None:
            push(remaining)
            return
        match, kind = best
        if match.start() > 0:
            push(remaining[: match.start()])
        if kind == "link":
            for span in parse_inline(match.group(1)):
                push(span.text, _combine(span.style, LINK), match.group(2))
        elif kind == "autolink":
            push(match.group(1), LINK, match.group(1))
        elif kind == "bare":
            push(match.group(0), LINK, match.group(0))
        elif kind == "bold_italic":
            for span in parse_inline(match.group(2)):
                push(span.text, BOLD_ITALIC, span.href)
        elif kind == "bold":
            for span in parse_inline(match.group(2)):
                push(span.text, _combine(span.style, BOLD), span.href)
        elif kind == "strike":
            for span in parse_inline(match.group(1)):
                push(span.text, _combine(span.style, STRIKE), span.href)
        elif kind == "italic":
            for span in parse_inline(match.group(2)):
                push(span.text, _combine(span.style, ITALIC), span.href)
        remaining = remaining[match.end():]


def _earliest(text: str) -> Optional[Tuple[re.Match, str]]:
    candidates = (
        (_LINK.search(text), "link"),
        (_AUTOLINK.search(text), "autolink"),
        (_BARE_URL.search(text), "bare"),
        (_BOLD_ITALIC.search(text), "bold_italic"),
        (_BOLD.search(text), "bold"),
        (_STRIKE.search(text), "strike"),
        (_ITALIC.search(text), "italic"),
    )
    best: Optional[Tuple[re.Match, str]] = None
    for match, kind in candidates:
        if match is None:
            continue
        if best is None or match.start() < best[0].start():
            best = (match, kind)
    return best


def _combine(style: str, addition: str) -> str:
    if style == PLAIN:
        return addition
    if addition in (BOLD, ITALIC) and style in (BOLD, ITALIC):
        return BOLD_ITALIC
    if addition in style.split("+"):
        return style
    return f"{style}+{addition}"


def _merge(spans: List[Span]) -> List[Span]:
    out: List[Span] = []
    for span in spans:
        if out and out[-1].style == span.style and out[-1].href == span.href:
            out[-1].text += span.text
        else:
            out.append(Span(span.text, span.style, span.href))
    return out


# --------------------------------------------------------------------------- #
# Block parsing
# --------------------------------------------------------------------------- #


def parse(text: str) -> List[Block]:
    """Parse a (possibly partial) Markdown document into blocks."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Block] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        # ---- display math ------------------------------------------- #
        if line.lstrip().startswith("$$"):
            source, index = _collect_math(lines, index)
            if source is not None:
                blocks.append(MathBlock(source))
                continue

        # ---- fenced code -------------------------------------------- #
        fence = _FENCE.match(line)
        if fence:
            indent, marker, language = fence.groups()
            code_lines: List[str] = []
            index += 1
            closed = False
            while index < total:
                if _FENCE.match(lines[index]) and _closes(lines[index], marker):
                    index += 1
                    closed = True
                    break
                code_lines.append(lines[index])
                index += 1
            stripped = [
                l[len(indent):] if l.startswith(indent) else l for l in code_lines
            ]
            while stripped and not stripped[0].strip():
                stripped.pop(0)
            while stripped and not stripped[-1].strip():
                stripped.pop()
            blocks.append(
                CodeBlock("\n".join(stripped), language.lower(), open=not closed)
            )
            continue

        # ---- horizontal rule ---------------------------------------- #
        if _RULE.match(line):
            blocks.append(Rule())
            index += 1
            continue

        # ---- heading ------------------------------------------------ #
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            blocks.append(Heading(level, parse_inline(heading.group(2).strip())))
            index += 1
            continue

        # ---- table -------------------------------------------------- #
        if "|" in line and index + 1 < total and _TABLE_SEP.match(lines[index + 1]):
            table, index = _parse_table(lines, index)
            if table is not None:
                blocks.append(table)
                continue

        # ---- block quote -------------------------------------------- #
        if _QUOTE.match(line):
            quote_lines: List[str] = []
            while index < total:
                match = _QUOTE.match(lines[index])
                if not match:
                    break
                quote_lines.append(match.group(1))
                index += 1
            blocks.append(Quote(parse_inline(" ".join(quote_lines).strip())))
            continue

        # ---- lists -------------------------------------------------- #
        bullet = _BULLET.match(line)
        ordered = _ORDERED.match(line)
        if bullet or ordered:
            items, index = _parse_list(lines, index)
            blocks.extend(items)
            continue

        # ---- paragraph ---------------------------------------------- #
        para_lines: List[str] = []
        while index < total:
            current = lines[index]
            if not current.strip():
                break
            if (
                _HEADING.match(current)
                or _FENCE.match(current)
                or _RULE.match(current)
                or _BULLET.match(current)
                or _ORDERED.match(current)
                or _QUOTE.match(current)
            ):
                break
            para_lines.append(current.strip())
            index += 1
        blocks.append(Paragraph(parse_inline(" ".join(para_lines))))

    return _trim_edges(blocks)


def _closes(line: str, marker: str) -> bool:
    match = _FENCE.match(line)
    if not match:
        return False
    return match.group(2)[0] == marker[0] and len(match.group(2)) >= len(marker)


def _collect_math(lines: List[str], index: int) -> Tuple[Optional[str], int]:
    first = lines[index].lstrip()
    body = first[2:]
    if body.rstrip().endswith("$$") and len(first.strip()) > 4:
        return body.rstrip()[:-2].strip(), index + 1
    collected: List[str] = []
    cursor = index + 1
    while cursor < len(lines):
        if "$$" in lines[cursor]:
            before = lines[cursor].split("$$", 1)[0]
            if before.strip():
                collected.append(before.strip())
            return "\n".join(collected).strip(), cursor + 1
        collected.append(lines[cursor].strip())
        cursor += 1
    return "\n".join(collected).strip(), cursor


def _parse_list(lines: List[str], index: int) -> Tuple[List[Block], int]:
    items: List[Block] = []
    ordered = bool(_ORDERED.match(lines[index]))
    number = 1
    while index < len(lines):
        line = lines[index]
        bullet = _BULLET.match(line)
        seq = _ORDERED.match(line)
        if not bullet and not seq:
            break
        if ordered != bool(seq):
            break
        if bullet:
            content = bullet.group(3)
            depth = len(bullet.group(1).expandtabs(4)) // 2
            number = 1
        else:
            content = seq.group(3)
            depth = len(seq.group(1).expandtabs(4)) // 2
            number = int(seq.group(2))
        index += 1
        parts = [content]
        while index < len(lines):
            nxt = lines[index]
            if not nxt.strip():
                if index + 1 < len(lines) and (
                    _BULLET.match(lines[index + 1]) or _ORDERED.match(lines[index + 1])
                ):
                    break
                if index + 1 < len(lines) and nxt.startswith((" ", "\t")):
                    index += 1
                    continue
                break
            if _BULLET.match(nxt) or _ORDERED.match(nxt):
                break
            if nxt.startswith((" ", "\t")):
                parts.append(nxt.strip())
                index += 1
                continue
            break
        items.append(
            ListItem(
                spans=parse_inline(" ".join(parts).strip()),
                ordered=ordered,
                number=number,
                depth=min(depth, 4),
            )
        )
        number += 1
    return items, index


def _parse_table(lines: List[str], index: int) -> Tuple[Optional[Table], int]:
    header_cells = _split_row(lines[index])
    if not header_cells:
        return None, index + 1
    index += 2  # header + separator
    rows: List[List[List[Span]]] = []
    while index < len(lines):
        line = lines[index]
        if not line.strip() or "|" not in line:
            break
        if _HEADING.match(line) or _FENCE.match(line) or _BULLET.match(line):
            break
        cells = _split_row(line)
        if cells:
            rows.append([parse_inline(c) for c in cells])
        index += 1
    return (Table(header=[parse_inline(c) for c in header_cells], rows=rows), index)


def _split_row(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells: List[str] = []
    current: List[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
            current.append(char)
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return [c for c in cells]


def _trim_edges(blocks: List[Block]) -> List[Block]:
    while blocks and isinstance(blocks[0], Spacer):
        blocks.pop(0)
    while blocks and isinstance(blocks[-1], Spacer):
        blocks.pop()
    return blocks


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def to_plain_text(text: str) -> str:
    """Strip markdown syntax (titles, clipboard, plain-text fallback)."""
    out: List[str] = []
    for block in parse(text):
        if isinstance(block, CodeBlock):
            out.append(block.code)
        elif isinstance(block, Heading):
            out.append(_spans_to_text(block.spans))
        elif isinstance(block, (Paragraph, Quote)):
            out.append(_spans_to_text(block.spans))
        elif isinstance(block, ListItem):
            prefix = f"{block.number}. " if block.ordered else "- "
            out.append(prefix + _spans_to_text(block.spans))
        elif isinstance(block, MathBlock):
            out.append(block.source)
        elif isinstance(block, Table):
            out.append(" | ".join(_spans_to_text(c) for c in block.header))
            for row in block.rows:
                out.append(" | ".join(_spans_to_text(c) for c in row))
        elif isinstance(block, Rule):
            out.append("---")
    return "\n".join(out).strip()


def _spans_to_text(spans: List[Span]) -> str:
    return "".join(
        (span.href if span.style == LINK and span.href else span.text) for span in spans
    )


def has_code_blocks(text: str) -> bool:
    return any(isinstance(b, CodeBlock) for b in parse(text))


def code_languages(text: str) -> List[str]:
    return [b.language for b in parse(text) if isinstance(b, CodeBlock) and b.language]
