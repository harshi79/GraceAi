"""Markdown parsing, including the partial-document cases streaming produces."""

from __future__ import annotations

import pytest

from grace import markdown_render as md


def types(blocks):
    return [type(b).__name__ for b in blocks]


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #

def test_plain_paragraph():
    blocks = md.parse("Hello world")
    assert types(blocks) == ["Paragraph"]
    assert md._spans_to_text(blocks[0].spans) == "Hello world"


def test_soft_line_breaks_join_into_one_paragraph():
    blocks = md.parse("one\ntwo\nthree")
    assert types(blocks) == ["Paragraph"]
    assert md._spans_to_text(blocks[0].spans) == "one two three"


def test_blank_line_separates_paragraphs():
    assert types(md.parse("one\n\ntwo")) == ["Paragraph", "Paragraph"]


@pytest.mark.parametrize(
    "source,level",
    [("# a", 1), ("## b", 2), ("### c", 3), ("#### d", 4), ("##### e", 5),
     ("###### f", 6)],
)
def test_headings(source, level):
    blocks = md.parse(source)
    assert types(blocks) == ["Heading"]
    assert blocks[0].level == level


def test_fenced_code_block():
    blocks = md.parse("```python\nprint('hi')\n```")
    assert types(blocks) == ["CodeBlock"]
    assert blocks[0].language == "python"
    assert blocks[0].code == "print('hi')"
    assert blocks[0].open is False


def test_code_block_without_language():
    blocks = md.parse("```\nplain\n```")
    assert blocks[0].language == ""
    assert blocks[0].code == "plain"


def test_tilde_fence():
    blocks = md.parse("~~~js\nconst a = 1;\n~~~")
    assert blocks[0].code == "const a = 1;"
    assert blocks[0].language == "js"


def test_unterminated_fence_is_open():
    blocks = md.parse("```python\nprint('partial')")
    assert types(blocks) == ["CodeBlock"]
    assert blocks[0].open is True
    assert blocks[0].code == "print('partial')"


def test_fence_contents_are_not_markdown_parsed():
    blocks = md.parse("```\n# not a heading\n**not bold**\n```")
    assert blocks[0].code == "# not a heading\n**not bold**"


def test_bullet_list():
    blocks = md.parse("- one\n- two\n* three")
    assert types(blocks) == ["ListItem"] * 3
    assert all(b.ordered is False for b in blocks)
    assert md._spans_to_text(blocks[0].spans) == "one"


def test_ordered_list():
    blocks = md.parse("1. one\n2. two")
    assert types(blocks) == ["ListItem"] * 2
    assert [b.number for b in blocks] == [1, 2]
    assert all(b.ordered for b in blocks)


def test_nested_list_depth():
    blocks = md.parse("- top\n  - nested")
    assert blocks[0].depth == 0
    assert blocks[1].depth == 1


def test_blockquote():
    blocks = md.parse("> quoted text")
    assert types(blocks) == ["Quote"]
    assert md._spans_to_text(blocks[0].spans) == "quoted text"


def test_horizontal_rule():
    assert types(md.parse("---")) == ["Rule"]
    assert types(md.parse("***")) == ["Rule"]


def test_table():
    source = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    blocks = md.parse(source)
    assert types(blocks) == ["Table"]
    assert len(blocks[0].header) == 2
    assert len(blocks[0].rows) == 2


def test_math_block():
    blocks = md.parse("$$\nx^2 + y^2 = z^2\n$$")
    assert types(blocks) == ["MathBlock"]
    assert blocks[0].source == "x^2 + y^2 = z^2"


def test_mixed_document():
    source = (
        "# Title\n\n"
        "Some **bold** text.\n\n"
        "- item one\n- item two\n\n"
        "```js\nlet a = 1;\n```\n\n"
        "> quote\n"
    )
    names = types(md.parse(source))
    assert names == ["Heading", "Paragraph", "ListItem", "ListItem",
                     "CodeBlock", "Quote"]


def test_empty_document():
    assert md.parse("") == []
    assert md.parse("\n\n\n") == []


# --------------------------------------------------------------------------- #
# Inline
# --------------------------------------------------------------------------- #

def styles(source):
    spans = md.parse_inline(source)
    return [(s.text, s.style) for s in spans]


def test_bold():
    assert styles("**bold**") == [("bold", "bold")]


def test_italic():
    assert styles("*it*") == [("it", "italic")]
    assert styles("_it_") == [("it", "italic")]


def test_bold_italic():
    assert styles("***both***") == [("both", "bold_italic")]


def test_strikethrough():
    assert styles("~~gone~~") == [("gone", "strike")]


def test_inline_code():
    assert styles("`code`") == [("code", "code")]


def test_inline_code_is_not_emphasis_parsed():
    assert styles("`**not bold**`") == [("**not bold**", "code")]


def test_link():
    spans = md.parse_inline("see [docs](https://example.com/x)")
    assert spans[1].style == "link"
    assert spans[1].href == "https://example.com/x"


def test_autolink():
    spans = md.parse_inline("<https://example.com>")
    assert spans[0].style == "link"
    assert spans[0].href == "https://example.com"


def test_bare_url():
    spans = md.parse_inline("visit https://example.com now")
    assert spans[1].style == "link"


def test_bold_inside_link():
    spans = md.parse_inline("[**b**](https://e.com)")
    assert spans[0].style == "bold+link"


def test_unclosed_emphasis_does_not_swallow():
    assert styles("**unclosed") == [("**unclosed", "plain")]


def test_adjacent_spans_are_merged():
    assert styles("plain text") == [("plain text", "plain")]


# --------------------------------------------------------------------------- #
# Plain text / helpers
# --------------------------------------------------------------------------- #

def test_to_plain_text_strips_markdown():
    source = "# Title\n\n**bold** and `code`\n\n- a\n- b\n"
    plain = md.to_plain_text(source)
    assert "Title" in plain
    assert "bold" in plain
    assert "a" in plain
    assert "**" not in plain
    assert "`" not in plain


def test_to_plain_text_includes_code():
    plain = md.to_plain_text("```py\nx = 1\n```")
    assert "x = 1" in plain


def test_has_code_blocks():
    assert md.has_code_blocks("```py\nx\n```")
    assert not md.has_code_blocks("no code here")


def test_code_languages():
    assert md.code_languages("```py\nx\n```\n```js\ny\n```") == ["py", "js"]


# --------------------------------------------------------------------------- #
# Streaming realism
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "partial",
    [
        "# He",
        "Some **bo",
        "```pyt",
        "```python\nprint(",
        "- item",
        "| a |",
        "$$\nx",
        "> quot",
    ],
)
def test_partial_documents_parse_without_error(partial):
    blocks = md.parse(partial)
    assert isinstance(blocks, list)


def test_progressive_growth():
    full = "# Title\n\nBody text with **emphasis**.\n\n```py\nprint(1)\n```"
    for i in range(1, len(full) + 1):
        md.parse(full[:i])  # must never raise


def test_long_document_performance():
    source = "\n\n".join(
        [f"## Section {i}\n\nSome text with **bold** and `code`." for i in range(400)]
    )
    blocks = md.parse(source)
    assert len(blocks) >= 800
