"""Renders :mod:`grace.markdown_render` blocks into a read-only ``tk.Text``.

Streaming answers are re-rendered wholesale, but throttled, and the renderer
is written so a partially-arrived document never raises: an unterminated code
fence simply renders as an open code block.

Every code block carries a real, clickable **Copy** affordance implemented
with a per-block Text tag - no nested widgets - so it keeps working at any
window size and survives re-renders during streaming.
"""

from __future__ import annotations

import time
import tkinter as tk
import webbrowser
from typing import Dict, List, Optional

from .. import markdown_render as md
from . import theme
from .widgets import ui_font

#: Minimum time between re-renders while streaming (seconds).
RENDER_THROTTLE = 0.055
#: Slower cadence once an answer gets long, to keep the UI responsive.
LONG_DOC_THROTTLE = 0.22
LONG_DOC_CHARS = 6000


class MarkdownView(tk.Frame):
    """A scroll-free, auto-sizing markdown surface."""

    def __init__(self, master, width_chars: int = 78, **kw):
        bg = kw.pop("background", theme.BG)
        super().__init__(master, bg=bg, **kw)
        self.width_chars = width_chars
        self._last_render = 0.0
        self._last_source = ""
        self._pending_after: Optional[str] = None
        self._block_counter = 0
        self._plain_cache = ""
        self._copy_registry: Dict[str, str] = {}
        self._pending_copy_tags: List[str] = []

        self.text = tk.Text(
            self,
            wrap="word",
            bg=bg,
            fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD),
            relief="flat",
            bd=0,
            padx=0,
            pady=0,
            cursor="arrow",
            exportselection=False,
            highlightthickness=0,
            spacing1=0,
            spacing2=0,
            spacing3=0,
            insertwidth=0,
        )
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")
        self._configure_tags()

    # ------------------------------------------------------------------ #
    def _configure_tags(self) -> None:
        t = self.text
        t.tag_configure(
            "body",
            font=ui_font(theme.SIZE_MD),
            foreground=theme.TEXT,
            spacing1=0,
            spacing3=6,
            lmargin1=0,
            lmargin2=0,
        )
        for level, size in ((1, theme.SIZE_2XL), (2, theme.SIZE_XL), (3, theme.SIZE_LG)):
            t.tag_configure(
                f"h{level}",
                font=ui_font(size, bold=True),
                foreground=theme.TEXT,
                spacing1=14 if level == 1 else 11,
                spacing3=5,
            )
        t.tag_configure("h4", font=ui_font(theme.SIZE_MD, bold=True),
                        foreground=theme.TEXT, spacing1=9, spacing3=4)
        t.tag_configure("h5", font=ui_font(theme.SIZE_BASE, bold=True),
                        foreground=theme.TEXT_MUTED, spacing1=8, spacing3=3)
        t.tag_configure("h6", font=ui_font(theme.SIZE_BASE, bold=True, italic=True),
                        foreground=theme.TEXT_MUTED, spacing1=8, spacing3=3)
        t.tag_configure("bold", font=ui_font(theme.SIZE_MD, bold=True))
        t.tag_configure("italic", font=ui_font(theme.SIZE_MD, italic=True))
        t.tag_configure("bold_italic",
                        font=ui_font(theme.SIZE_MD, bold=True, italic=True))
        t.tag_configure("strike", font=ui_font(theme.SIZE_MD), overstrike=True,
                        foreground=theme.TEXT_FAINT)
        t.tag_configure(
            "code",
            font=ui_font(theme.SIZE_SM, mono=True),
            foreground=theme.CODE_TEXT,
            background=theme.CODE_BG,
            spacing1=1,
            spacing3=1,
            lmargin1=12,
            lmargin2=12,
            rmargin=12,
        )
        t.tag_configure(
            "code_header",
            font=ui_font(theme.SIZE_XS),
            foreground=theme.TEXT_FAINT,
            background=theme.CODE_HEADER,
            spacing1=8,
            spacing3=0,
            lmargin1=12,
            lmargin2=12,
            rmargin=12,
        )
        t.tag_configure(
            "code_copy",
            font=ui_font(theme.SIZE_XS, bold=True),
            foreground=theme.ACCENT,
            background=theme.CODE_HEADER,
            spacing1=8,
            spacing3=0,
        )
        t.tag_configure(
            "quote",
            font=ui_font(theme.SIZE_MD, italic=True),
            foreground=theme.TEXT_MUTED,
            lmargin1=14,
            lmargin2=14,
            rmargin=10,
            spacing1=6,
            spacing3=6,
        )
        t.tag_configure("bullet", foreground=theme.ACCENT,
                        font=ui_font(theme.SIZE_MD, bold=True), lmargin1=6, lmargin2=20)
        t.tag_configure("list_text", lmargin1=6, lmargin2=20, spacing3=3)
        t.tag_configure("rule", foreground=theme.BORDER_2, spacing1=9, spacing3=9,
                        font=ui_font(theme.SIZE_SM))
        t.tag_configure("math_label", foreground=theme.TEXT_FAINT,
                        font=ui_font(theme.SIZE_XS), background=theme.SURFACE_2,
                        spacing1=8, spacing3=0, lmargin1=12, rmargin=12)
        t.tag_configure("math_body", foreground=theme.TEXT_MUTED,
                        font=ui_font(theme.SIZE_SM, mono=True),
                        background=theme.SURFACE_2, spacing3=8, lmargin1=12,
                        lmargin2=12, rmargin=12)
        t.tag_configure("table_head", font=ui_font(theme.SIZE_SM, bold=True),
                        foreground=theme.TEXT_MUTED, spacing1=8, spacing3=2)
        t.tag_configure("table_cell", font=ui_font(theme.SIZE_SM),
                        foreground=theme.TEXT, spacing3=2)
        t.tag_configure("link", foreground=theme.LINK_COLOR, underline=True)
        t.tag_configure("meta", foreground=theme.TEXT_FAINT,
                        font=ui_font(theme.SIZE_XS), spacing1=2, spacing3=0)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def set_markdown(self, source: str, *, final: bool = False, force: bool = False) -> None:
        """Render ``source``; while streaming this is throttled."""
        if source == self._last_source and not force:
            return
        now = time.monotonic()
        if not final and not force:
            if now - self._last_render < self._throttle_for(source):
                if self._pending_after is None:
                    self._pending_after = self.after(
                        int(self._throttle_for(source) * 1000) + 12,
                        lambda: self._flush_pending(source),
                    )
                return
        self._render(source)

    def _flush_pending(self, source: str) -> None:
        self._pending_after = None
        if source != self._last_source:
            self._render(source)

    def _throttle_for(self, source: str) -> float:
        if len(source) > LONG_DOC_CHARS:
            return LONG_DOC_THROTTLE
        return RENDER_THROTTLE

    def set_plain(self, text: str) -> None:
        """Render raw text with no markdown (used for errors / notices)."""
        self._plain_cache = text
        self._last_source = f"\x00{text}"
        self._last_render = time.monotonic()
        self._apply([("body", [(text, "body")])] if text else [])

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._last_source = ""
        self._last_render = 0.0
        self._plain_cache = ""
        self._copy_registry = {}
        self._pending_copy_tags = []

    def copy_all(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self._plain_cache)
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def _render(self, source: str) -> None:
        self._last_render = time.monotonic()
        self._last_source = source
        self._plain_cache = source
        self._copy_registry = {}
        self._pending_copy_tags = []
        blocks = md.parse(source)
        lines: List[tuple] = []
        for block in blocks:
            self._emit_block(block, lines)
        self._apply(lines)

    def _emit_block(self, block, lines: List[tuple]) -> None:
        if isinstance(block, md.Heading):
            lines.append((f"h{block.level}", [(_spans(block.spans), "body")]))
        elif isinstance(block, md.Paragraph):
            lines.append(("body", [(_spans(block.spans), "body")]))
        elif isinstance(block, md.Quote):
            lines.append(("quote", [("▌ ", "bullet"), (_spans(block.spans), "body")]))
        elif isinstance(block, md.Rule):
            lines.append(("rule", [("─" * 46, "rule")]))
        elif isinstance(block, md.ListItem):
            indent = "    " * min(block.depth, 4)
            marker = f"{block.number}." if block.ordered else "•"
            lines.append(
                (
                    "list_text",
                    [
                        (f"{indent}", "list_text"),
                        (f"{marker} ", "bullet"),
                        (_spans(block.spans), "body"),
                    ],
                )
            )
        elif isinstance(block, md.CodeBlock):
            self._emit_code(block, lines)
        elif isinstance(block, md.MathBlock):
            lines.append(("math_label", [("LaTeX", "math_label")]))
            for line in block.source.split("\n"):
                lines.append(("math_body", [(line, "math_body")]))
        elif isinstance(block, md.Table):
            self._emit_table(block, lines)

    def _emit_code(self, block: md.CodeBlock, lines: List[tuple]) -> None:
        self._block_counter += 1
        copy_tag = f"copy-{self._block_counter}"
        language = block.language or ("text" if not block.open else block.language)
        header = f"  {language or 'code'}"
        if block.open:
            header += "  ·  streaming"
        lines.append(
            (
                "code_header",
                [
                    (header, "code_header"),
                    ("        Copy", "code_copy"),
                ],
            )
        )
        self._copy_registry[copy_tag] = block.code
        for line in block.code.split("\n"):
            lines.append(("code", [(line if line else " ", "code")]))
        lines.append(("code", [(" ", "code")]))
        self._pending_copy_tags.append(copy_tag)

    def _emit_table(self, block: md.Table, lines: List[tuple]) -> None:
        def row(cells: List[List[md.Span]]) -> str:
            return "  │  ".join(_spans(c) for c in cells)

        lines.append(("table_head", [(row(block.header), "table_head")]))
        lines.append(("rule", [("─" * 46, "rule")]))
        for cells in block.rows:
            lines.append(("table_cell", [(row(cells), "table_cell")]))

    # ------------------------------------------------------------------ #
    def _apply(self, lines: List[tuple]) -> None:
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")

        for base_tag, chunks in lines:
            start = text.index("end - 1 chars")
            for content, tag in chunks:
                text.insert("end", content, (base_tag, tag))
            end = text.index("end - 1 chars")
            if base_tag:
                text.tag_add(base_tag, start, end)
            text.insert("end", "\n", (base_tag,))

        for tag in self._pending_copy_tags:
            text.tag_bind(tag, "<Button-1>", lambda e, t=tag: self._copy_block(t))
            text.tag_bind(tag, "<Enter>", lambda e: text.configure(cursor="hand2"))
            text.tag_bind(tag, "<Leave>", lambda e: text.configure(cursor="arrow"))
            text.tag_configure(tag, foreground=theme.ACCENT_HOVER)

        text.tag_bind("link", "<Button-1>", self._open_link)
        text.tag_bind("link", "<Enter>", lambda e: text.configure(cursor="hand2"))
        text.tag_bind("link", "<Leave>", lambda e: text.configure(cursor="arrow"))

        text.configure(state="disabled")
        text.see("1.0")

    def _copy_block(self, tag: str) -> None:
        code = self._copy_registry.get(tag, "")
        if not code:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(code)
            self._flash_copied(tag)
        except Exception:  # pragma: no cover - defensive
            pass

    def _flash_copied(self, tag: str) -> None:
        self.text.tag_configure(tag, foreground=theme.SUCCESS)
        self.after(900, lambda: self.text.tag_configure(tag, foreground=theme.ACCENT))

    def _open_link(self, event) -> None:
        try:
            index = self.text.index(f"@{event.x},{event.y}")
            ranges = self.text.tag_ranges("link")
            for i in range(0, len(ranges), 2):
                if self.text.compare(ranges[i], "<=", index) and self.text.compare(
                    index, "<", ranges[i + 1]
                ):
                    href = self.text.get(ranges[i], ranges[i + 1])
                    break
            else:
                return
            if href.startswith(("http://", "https://")):
                webbrowser.open(href)
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ #
    def height_estimate(self) -> int:
        return max(1, len(self._plain_cache.split("\n")))


def _spans(spans: List[md.Span]) -> str:
    return "".join(s.text for s in spans)
