"""Left rail: Aero branding, Grace profile + credits, the current
conversation, the signed-in account and connection state."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from ..models import Conversation, Credits, User
from . import theme
from .widgets import Avatar, Card, PillButton, Separator, ui_font


class Sidebar(tk.Frame):
    WIDTH = theme.SIDEBAR_WIDTH

    def __init__(self, master, on_sign_out: Callable[[], None], **kw):
        bg = kw.pop("background", theme.SURFACE)
        super().__init__(master, bg=bg, width=self.WIDTH, **kw)
        self.pack_propagate(False)
        self._on_sign_out = on_sign_out

        self._build_brand()
        self._build_grace_card()
        self._build_conversation_card()
        self._build_account_card()
        self._build_footer()

    # ------------------------------------------------------------------ #
    def _build_brand(self) -> None:
        row = tk.Frame(self, bg=theme.SURFACE)
        row.pack(fill="x", padx=16, pady=(16, 12))

        mark = tk.Frame(row, bg=theme.ACCENT, width=30, height=30)
        mark.pack(side="left")
        mark.pack_propagate(False)
        tk.Label(
            mark, text="A", bg=theme.ACCENT, fg=theme.TEXT_ON_ACCENT,
            font=ui_font(theme.SIZE_LG, bold=True),
        ).pack(expand=True)

        stack = tk.Frame(row, bg=theme.SURFACE)
        stack.pack(side="left", padx=(11, 0))
        tk.Label(
            stack, text="Aero", bg=theme.SURFACE, fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD, bold=True), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            stack, text="Grace 2.0", bg=theme.SURFACE, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS), anchor="w",
        ).pack(anchor="w")

    # ------------------------------------------------------------------ #
    def _build_grace_card(self) -> None:
        card = Card(self, bg=theme.SURFACE_2, border=theme.BORDER)
        card.pack(fill="x", padx=12, pady=(4, 10))

        row = tk.Frame(card, bg=theme.SURFACE_2)
        row.pack(fill="x", padx=12, pady=(12, 0))
        Avatar(row, initials="G", size=30, background=theme.SURFACE).pack(side="left")
        tk.Label(
            row, text="Grace", bg=theme.SURFACE_2, fg=theme.TEXT,
            font=ui_font(theme.SIZE_MD, bold=True),
        ).pack(side="left", padx=(10, 0))
        tk.Label(
            row, text="ready", bg=theme.SURFACE_2, fg=theme.SUCCESS,
            font=ui_font(theme.SIZE_XS),
        ).pack(side="right")

        self.credits_label = tk.Label(
            card, text="Grace credits  —", bg=theme.SURFACE_2, fg=theme.TEXT_MUTED,
            font=ui_font(theme.SIZE_SM), anchor="w",
        )
        self.credits_label.pack(fill="x", padx=12, pady=(9, 0))

        self.credits_detail = tk.Label(
            card, text="Balance appears after your first answer.",
            bg=theme.SURFACE_2, fg=theme.TEXT_FAINT, font=ui_font(theme.SIZE_XS),
            anchor="w", wraplength=self.WIDTH - 48, justify="left",
        )
        self.credits_detail.pack(fill="x", padx=12, pady=(3, 12))

    # ------------------------------------------------------------------ #
    def _build_conversation_card(self) -> None:
        tk.Label(
            self, text="CONVERSATION", bg=theme.SURFACE, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS, bold=True), anchor="w",
        ).pack(fill="x", padx=16, pady=(6, 6))

        card = Card(self, bg=theme.SURFACE_2, border=theme.BORDER)
        card.pack(fill="x", padx=12)

        self.convo_title = tk.Label(
            card, text="New conversation", bg=theme.SURFACE_2, fg=theme.TEXT,
            font=ui_font(theme.SIZE_SM, bold=True), anchor="w",
            wraplength=self.WIDTH - 48, justify="left",
        )
        self.convo_title.pack(fill="x", padx=12, pady=(11, 0))

        self.convo_meta = tk.Label(
            card, text="No messages yet", bg=theme.SURFACE_2, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS), anchor="w",
        )
        self.convo_meta.pack(fill="x", padx=12, pady=(3, 11))

    # ------------------------------------------------------------------ #
    def _build_account_card(self) -> None:
        tk.Frame(self, bg=theme.SURFACE).pack(fill="both", expand=True)

        card = Card(self, bg=theme.SURFACE_2, border=theme.BORDER)
        card.pack(fill="x", padx=12, pady=(0, 8))

        row = tk.Frame(card, bg=theme.SURFACE_2)
        row.pack(fill="x", padx=12, pady=(12, 0))
        self.account_avatar = Avatar(row, initials="?", size=30, background=theme.SURFACE)
        self.account_avatar.pack(side="left")
        stack = tk.Frame(row, bg=theme.SURFACE_2)
        stack.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.account_name = tk.Label(
            stack, text="Not signed in", bg=theme.SURFACE_2, fg=theme.TEXT,
            font=ui_font(theme.SIZE_SM, bold=True), anchor="w",
        )
        self.account_name.pack(anchor="w")
        self.account_handle = tk.Label(
            stack, text="", bg=theme.SURFACE_2, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS), anchor="w",
        )
        self.account_handle.pack(anchor="w")

        self.plan_label = tk.Label(
            card, text="", bg=theme.SURFACE_2, fg=theme.TEXT_MUTED,
            font=ui_font(theme.SIZE_XS), anchor="w",
        )
        self.plan_label.pack(fill="x", padx=12, pady=(7, 12))

    # ------------------------------------------------------------------ #
    def _build_footer(self) -> None:
        Separator(self, color=theme.BORDER).pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg=theme.SURFACE)
        footer.pack(fill="x", side="bottom", padx=12, pady=(0, 12))

        self.connection = tk.Label(
            footer, text="Connecting…", bg=theme.SURFACE, fg=theme.TEXT_FAINT,
            font=ui_font(theme.SIZE_XS), anchor="w",
        )
        self.connection.pack(fill="x", pady=(8, 8))

        PillButton(
            footer, text="Sign out", command=self._on_sign_out, variant="subtle",
            width=self.WIDTH - 24, height=28, font_size=theme.SIZE_SM,
        ).pack(fill="x")

    # ------------------------------------------------------------------ #
    # Updates
    # ------------------------------------------------------------------ #
    def set_user(self, user: Optional[User]) -> None:
        if user is None:
            self.account_name.configure(text="Not signed in")
            self.account_handle.configure(text="")
            self.account_avatar.set_initials("?")
            self.plan_label.configure(text="")
            return
        self.account_name.configure(text=user.display_name)
        self.account_handle.configure(text=user.handle)
        self.account_avatar.set_initials(_initials(user.display_name))
        plan = user.plan.strip()
        self.plan_label.configure(
            text=f"Aero {plan.title()}" if plan else "Aero account"
        )

    def set_credits(self, credits: Optional[Credits]) -> None:
        if credits is None or credits.remaining is None:
            self.credits_label.configure(text="Grace credits  —")
            self.credits_detail.configure(text="Balance appears after your first answer.")
            return
        self.credits_label.configure(text=f"Grace credits  {credits.remaining:g}")
        detail = credits.label
        if credits.used is not None:
            detail = f"{credits.used:g} used  ·  {credits.remaining:g} left"
        if credits.tier:
            detail += f"  ·  {credits.tier}"
        self.credits_detail.configure(text=detail)

    def set_conversation(self, conversation: Optional[Conversation]) -> None:
        if conversation is None:
            self.convo_title.configure(text="New conversation")
            self.convo_meta.configure(text="No messages yet")
            return
        self.convo_title.configure(text=conversation.title)
        count = len(conversation.messages)
        if count == 0:
            self.convo_meta.configure(text="No messages yet")
        elif count == 1:
            self.convo_meta.configure(text="1 message")
        else:
            self.convo_meta.configure(text=f"{count} messages")

    def set_connection(self, state: str, detail: str = "") -> None:
        color = {
            "online": theme.SUCCESS,
            "connecting": theme.WARN,
            "offline": theme.DANGER,
        }.get(state, theme.TEXT_FAINT)
        dot = {"online": "●", "connecting": "◐", "offline": "○"}.get(state, "○")
        label = {"online": "Connected", "connecting": "Connecting",
                 "offline": "Offline"}.get(state, state)
        self.connection.configure(text=f"{dot} {label}", fg=color)
        if detail:
            self.connection.configure(text=f"{dot} {label} — {detail}")


def _initials(name: str) -> str:
    parts = [p for p in (name or "").replace("@", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
