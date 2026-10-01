"""The message list: bubbles, streaming surface, empty state and history.

Layout rules taken from the shipped Aero web client: a full-width left
aligned assistant surface (no bubble chrome), a compact right-aligned user
bubble, a slim avatar on assistant turns, timestamps under each turn, and an
empty state that offers four concrete starting points.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional

from ..models import Attachment, Conversation, Message, ROLE_USER
from . import theme
from .markdown_view import MarkdownView
from .widgets import Avatar, ScrollableFrame, ui_font

EMPTY_HEADLINE = "What are we working on?"
EMPTY_SUBTITLE = "Grace helps you think, write, debug, plan, and make decisions."
EMPTY_PRIVACY = "Grace cannot read your chat and dock messages."
SUGGESTIONS = (
    "Turn this idea into a plan",
    "Find the flaw in my strategy",
    "Debug this error with me",
    "Sharpen this into a pitch",
)
THINKING_LABEL = "Grace is thinking…"


class MessageBubble(tk.Frame):
    """One conversation turn."""

    def __init__(self, master, message: Message, on_copy=None, **kw):
        bg = kw.pop("background", theme.BG)
        super().__init__(master, bg=bg, **kw)
        self.message = message
        self.on_copy = on_copy
        self.is_user = message.role == ROLE_USER

        if self.is_user:
            self._build_user()
        else:
            self._build_assistant()

    # ------------------------------------------------------------------ #
    # User turn
    # ------------------------------------------------------------------ #
    def _build_user(self) -> None:
        outer = tk.Frame(self, bg=theme.BG)
        outer.pack(fill="x", padx=theme.MSG_PAD_X, pady=(theme.MSG_GAP // 2, 0))
        outer.columnconfigure(0, weight=1)

        bubble = tk.Frame(
            outer,
            bg=theme.BUBBLE_USER,
            highlightbackground=theme.BUBBLE_USER_BORDER,
            highlightthickness=1,
            bd=0,
        )
        bubble.pack(side="right", anchor="e")

        body = tk.Frame(bubble, bg=theme.BUBBLE_USER)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        if self.message.attachments:
            chips = tk.Frame(body, bg=theme.BUBBLE_USER)
            chips.pack(fill="x", pady=(0, 7))
            for attachment in self.message.attachments:
                self._attachment_chip(chips, attachment)

        text = tk.Text(
            body,
            wrap="word",
            bg=theme.BUBBLE_USER,
            fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD),
            relief="flat",
            bd=0,
            padx=0,
            pady=0,
            highlightthickness=0,
            cursor="arrow",
            exportselection=False,
            insertwidth=0,
            width=48,
        )
        text.insert("1.0", self.message.content)
        text.configure(state="disabled")
        text.pack(fill="x", expand=True)

        stamp = tk.Label(
            body,
            text=_clock(self.message.at),
            bg=theme.BUBBLE_USER,
            fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS),
            anchor="e",
        )
        stamp.pack(fill="x", pady=(6, 0))

    def _attachment_chip(self, master, attachment: Attachment) -> None:
        chip = tk.Frame(
            master,
            bg=theme.SURFACE_3,
            highlightbackground=theme.BORDER_2,
            highlightthickness=1,
            bd=0,
        )
        chip.pack(side="left", padx=(0, 6), pady=2)
        tk.Label(
            chip,
            text=f"{attachment.name}",
            bg=theme.SURFACE_3,
            fg=theme.TEXT_MUTED,
            font=ui_font(theme.SIZE_XS),
            padx=7,
            pady=3,
        ).pack(side="left")

    # ------------------------------------------------------------------ #
    # Assistant turn
    # ------------------------------------------------------------------ #
    def _build_assistant(self) -> None:
        outer = tk.Frame(self, bg=theme.BG)
        outer.pack(fill="x", padx=theme.MSG_PAD_X, pady=(theme.MSG_GAP, 0))
        outer.columnconfigure(1, weight=1)

        Avatar(outer, initials="G", size=26).grid(row=0, column=0, sticky="n", padx=(0, 12),
                                                  pady=(2, 0))

        body = tk.Frame(outer, bg=theme.BG)
        body.grid(row=0, column=1, sticky="nsew")

        self.status_label = tk.Label(
            body,
            text="",
            bg=theme.BG,
            fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_SM, italic=True),
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 4))

        self.view = MarkdownView(body, background=theme.BG)
        self.view.pack(fill="x", expand=True)
        if self.message.content:
            self.view.set_markdown(self.message.content, final=not self.message.streaming)

        self.footer = tk.Frame(body, bg=theme.BG)
        self.footer.pack(fill="x", pady=(6, 0))
        self._render_footer()

    # ------------------------------------------------------------------ #
    def _render_footer(self) -> None:
        for child in self.footer.winfo_children():
            child.destroy()
        parts: List[str] = []
        if self.message.at:
            parts.append(_clock(self.message.at))
        meta = self.message.meta or {}
        tier = str(meta.get("tier") or "")
        if tier:
            label = tier.replace("_", " ").title()
            if meta.get("thinking"):
                label += " · Thinking"
            parts.append(label)
        used = meta.get("usedCredits")
        if isinstance(used, (int, float)):
            parts.append(f"{used:g} credits")
        if self.message.error:
            parts.append("incomplete")
        if not parts:
            return
        tk.Label(
            self.footer,
            text="   ·   ".join(parts),
            bg=theme.BG,
            fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS),
            anchor="w",
        ).pack(side="left")

        if self.message.content:
            copy = tk.Label(
                self.footer,
                text="Copy",
                bg=theme.BG,
                fg=theme.TEXT_FAINT,
                font=ui_font(theme.SIZE_XS),
                cursor="hand2",
            )
            copy.pack(side="right")
            copy.bind("<Button-1>", lambda e: self._copy())
            copy.bind("<Enter>", lambda e: copy.configure(fg=theme.TEXT))
            copy.bind("<Leave>", lambda e: copy.configure(fg=theme.TEXT_FAINT))

    def _copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.message.content)
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ #
    def set_streaming_text(self, text: str) -> None:
        if self.is_user:
            return
        self.message.content = text
        self.view.set_markdown(text, final=False)

    def set_status(self, label: str) -> None:
        if self.is_user:
            return
        self.status_label.configure(text=label or "")

    def finalize(self, result=None) -> None:
        self.message.streaming = False
        if not self.is_user:
            self.view.set_markdown(self.message.content, final=True, force=True)
            self.status_label.configure(text="")
            if result is not None:
                meta = getattr(result, "extra", None) or {}
                self.message.meta = {
                    "tier": getattr(result, "tier", ""),
                    "thinking": getattr(result, "thinking", None),
                    "effort": getattr(result, "effort", ""),
                    "usedCredits": getattr(result, "credits_used", None),
                    "remainingCredits": getattr(result, "remaining_credits", None),
                    "updatedAt": meta.get("updatedAt", ""),
                }
            self._render_footer()

    def mark_error(self) -> None:
        self.message.error = True
        if not self.is_user:
            self.view.set_markdown(self.message.content, final=True, force=True)
            self.status_label.configure(text="Answer incomplete")
            self._render_footer()


def _clock(value: str) -> str:
    if not value:
        return ""
    text = str(value)
    if "T" in text:
        time_part = text.split("T", 1)[1]
        return time_part[:5]
    return text[-8:-3] if len(text) > 8 else text


# --------------------------------------------------------------------------- #
# Empty state
# --------------------------------------------------------------------------- #


class EmptyState(tk.Frame):
    def __init__(self, master, on_suggestion: Callable[[str], None], **kw):
        bg = kw.pop("background", theme.BG)
        super().__init__(master, bg=bg, **kw)
        self.on_suggestion = on_suggestion

        holder = tk.Frame(self, bg=bg)
        holder.pack(expand=True, pady=(40, 60))

        Avatar(holder, initials="G", size=44).pack(pady=(0, 18))
        tk.Label(
            holder, text=EMPTY_HEADLINE, bg=bg, fg=theme.TEXT,
            font=ui_font(theme.SIZE_2XL, bold=True),
        ).pack()
        tk.Label(
            holder, text=EMPTY_SUBTITLE, bg=bg, fg=theme.TEXT_MUTED,
            font=ui_font(theme.SIZE_MD), pady=8,
        ).pack()
        tk.Label(
            holder, text=EMPTY_PRIVACY, bg=bg, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS),
        ).pack(pady=(10, 26))

        grid = tk.Frame(holder, bg=bg)
        grid.pack()
        for index, suggestion in enumerate(SUGGESTIONS):
            card = tk.Frame(
                grid,
                bg=theme.SURFACE_2,
                highlightbackground=theme.BORDER,
                highlightthickness=1,
                bd=0,
                cursor="hand2",
            )
            card.grid(row=index // 2, column=index % 2, padx=6, pady=6, sticky="nsew")
            label = tk.Label(
                card, text=suggestion, bg=theme.SURFACE_2, fg=theme.TEXT_MUTED,
                font=ui_font(theme.SIZE_SM), justify="left", anchor="w", padx=14, pady=11,
                wraplength=210,
            )
            label.pack(fill="both", expand=True)
            for widget in (card, label):
                widget.bind("<Button-1>", lambda e, s=suggestion: self.on_suggestion(s))
                widget.bind("<Enter>", lambda e, c=card, l=label: _hover(c, l, True))
                widget.bind("<Leave>", lambda e, c=card, l=label: _hover(c, l, False))


def _hover(card: tk.Frame, label: tk.Label, on: bool) -> None:
    card.configure(bg=theme.SURFACE_3 if on else theme.SURFACE_2)
    label.configure(bg=theme.SURFACE_3 if on else theme.SURFACE_2,
                    fg=theme.TEXT if on else theme.TEXT_MUTED)


# --------------------------------------------------------------------------- #
# Message list
# --------------------------------------------------------------------------- #


class ChatView(tk.Frame):
    """Owns the scrollable list of turns."""

    def __init__(self, master, **kw):
        bg = kw.pop("background", theme.BG)
        super().__init__(master, bg=bg, **kw)
        self._bubbles: Dict[str, MessageBubble] = {}
        self._empty: Optional[EmptyState] = None
        self._stream_anchor: Optional[str] = None

        self.scroll = ScrollableFrame(self, bg=bg)
        self.scroll.pack(fill="both", expand=True)
        self.scroll.bind_wheel()
        self.list = self.scroll.inner

    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        self._bubbles = {}
        self._empty = None
        self._stream_anchor = None

    def show_empty_state(self, on_suggestion: Callable[[str], None]) -> None:
        self.clear()
        self._empty = EmptyState(self.list, on_suggestion, background=theme.BG)
        self._empty.pack(fill="both", expand=True)

    def render_conversation(self, conversation: Conversation) -> None:
        self.clear()
        if not conversation.messages:
            return
        for message in conversation.messages:
            self.append_message(message)

    def append_message(self, message: Message) -> MessageBubble:
        if self._empty is not None:
            self._empty.destroy()
            self._empty = None
        bubble = MessageBubble(self.list, message)
        bubble.pack(fill="x")
        self._bubbles[message.id] = bubble
        return bubble

    def bubble_for(self, message_id: str) -> Optional[MessageBubble]:
        return self._bubbles.get(message_id)

    # ------------------------------------------------------------------ #
    def auto_scroll(self) -> None:
        """Follow the stream only when the reader is already at the bottom."""
        if self.scroll.at_bottom():
            self.scroll.scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        self.scroll.scroll_to_bottom()
