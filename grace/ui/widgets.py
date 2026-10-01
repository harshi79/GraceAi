"""Reusable Tk widgets: rounded buttons, cards, scroll frames, avatars, toasts.

Everything is built on plain ``tk`` (no ttk theming) so the golden-green
palette is applied consistently.  Rounded rectangles are approximated with a
sampled polygon because Tk's canvas has no native rounded-rect item.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, List, Optional, Tuple

from . import theme

# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


def rounded_points(
    x0: float, y0: float, x1: float, y1: float, radius: float, steps: int = 6
) -> List[float]:
    """Perimeter samples for a rounded rectangle, ready for ``create_polygon``."""
    radius = max(0.0, min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    pts: List[Tuple[float, float]] = []

    def arc(cx: float, cy: float, start: float, end: float) -> None:
        for i in range(steps + 1):
            angle = math.radians(start + (end - start) * i / steps)
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

    pts.append((x0 + radius, y0))
    if x1 - x0 > 2 * radius:
        pts.append((x1 - radius, y0))
    arc(x1 - radius, y0 + radius, -90, 0)
    if y1 - y0 > 2 * radius:
        pts.append((x1, y1 - radius))
    arc(x1 - radius, y1 - radius, 0, 90)
    if x1 - x0 > 2 * radius:
        pts.append((x0 + radius, y1))
    arc(x0 + radius, y1 - radius, 90, 180)
    if y1 - y0 > 2 * radius:
        pts.append((x0, y0 + radius))
    arc(x0 + radius, y0 + radius, 180, 270)
    flat: List[float] = []
    for x, y in pts:
        flat.extend((round(x, 2), round(y, 2)))
    return flat


def bg_or(widget, fallback: str) -> str:
    try:
        value = widget.cget("bg")
        return value if value else fallback
    except Exception:  # pragma: no cover - defensive
        return fallback


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #


class PillButton(tk.Canvas):
    """A rounded, hover-aware button drawn on a canvas."""

    def __init__(
        self,
        master,
        text: str = "",
        command: Optional[Callable[[], None]] = None,
        *,
        variant: str = "ghost",
        glyph: str = "",
        width: int = 92,
        height: int = 30,
        radius: int = 8,
        font_size: int = theme.SIZE_BASE,
        bold: bool = False,
        state: str = "normal",
        **kwargs,
    ) -> None:
        bg = kwargs.pop("background", theme.SURFACE_2)
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2" if state == "normal" else "arrow",
            **kwargs,
        )
        self.command = command
        self.variant = variant
        self.text = text
        self.glyph = glyph
        self.radius = radius
        self.font_size = font_size
        self.bold = bold
        self._width = width
        self._height = height
        self._state = state
        self._hover = False
        self._pressed = False

        self._font = self._make_font()
        self._draw()

        for sequence in ("<Enter>", "<Leave>", "<ButtonPress-1>", "<ButtonRelease-1>"):
            self.bind(sequence, self._on_event)
        if state == "normal":
            self.configure(cursor="hand2")

    def _make_font(self):
        import tkinter.font as tkfont

        return tkfont.Font(
            family=theme.font_family("sans"),
            size=self.font_size,
            weight="bold" if self.bold else "normal",
        )

    def _palette(self) -> Tuple[str, str, str]:
        v = self.variant
        if v == "accent":
            if self._pressed:
                return theme.ACCENT_ACTIVE, theme.TEXT_ON_ACCENT, theme.ACCENT_ACTIVE
            if self._hover:
                return theme.ACCENT_HOVER, theme.TEXT_ON_ACCENT, theme.ACCENT_HOVER
            return theme.ACCENT, theme.TEXT_ON_ACCENT, theme.ACCENT
        if v == "danger":
            return theme.DANGER_WASH, theme.DANGER, theme.DANGER
        if v == "subtle":
            base = theme.SURFACE_3 if self._hover else theme.SURFACE_2
            return base, theme.TEXT_MUTED, theme.BORDER_2
        base = theme.SURFACE_3 if self._hover else bg_or(self, theme.SURFACE_2)
        return base, theme.TEXT if self._hover else theme.TEXT_MUTED, theme.BORDER

    def _draw(self) -> None:
        fill, fg, border = self._palette()
        self.delete("all")
        pad = 1
        self.create_polygon(
            *rounded_points(pad, pad, self._width - pad, self._height - pad, self.radius),
            smooth=True,
            splinesteps=12,
            fill=fill,
            outline=border,
            width=1,
        )
        label = f"{self.glyph} {self.text}" if self.glyph and self.text else (
            self.glyph or self.text
        )
        if label:
            self.create_text(
                self._width / 2,
                self._height / 2,
                text=label,
                fill=fg,
                font=self._font,
                anchor="center",
            )

    def _on_event(self, event) -> None:
        kind = getattr(event, "type", None)
        if self._state != "normal":
            return
        if kind == tk.EventType.Enter:
            self._hover = True
            self.configure(cursor="hand2")
        elif kind == tk.EventType.Leave:
            self._hover = False
            self._pressed = False
        elif kind == tk.EventType.ButtonPress:
            self._pressed = True
        elif kind == tk.EventType.ButtonRelease and self._pressed:
            self._pressed = False
            if self.command:
                self.command()
        self._draw()

    def set_text(self, text: str) -> None:
        self.text = text
        self._draw()

    def set_state(self, state: str) -> None:
        self._state = state
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self._draw()

    def set_size(self, width: int, height: int) -> None:
        self._width, self._height = width, height
        self.configure(width=width, height=height)
        self._draw()


class IconButton(PillButton):
    """Square button carrying a single glyph."""

    def __init__(self, master, glyph: str = "", command=None, **kwargs):
        size = kwargs.pop("size", 30)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("variant", "ghost")
        kwargs.setdefault("font_size", theme.SIZE_MD)
        super().__init__(master, command=command, glyph=glyph, **kwargs)


class SendButton(tk.Canvas):
    """Compact circular send button with a drawn arrow."""

    def __init__(self, master, command=None, diameter: int = 34, **kwargs):
        bg = kwargs.pop("background", theme.SURFACE_2)
        super().__init__(
            master,
            width=diameter,
            height=diameter,
            bg=bg,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.command = command
        self.d = diameter
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._draw()
        for sequence in ("<Enter>", "<Leave>", "<ButtonPress-1>", "<ButtonRelease-1>"):
            self.bind(sequence, self._on_event)

    def _draw(self) -> None:
        self.delete("all")
        if self._enabled:
            if self._pressed:
                fill = theme.ACCENT_ACTIVE
            elif self._hover:
                fill = theme.ACCENT_HOVER
            else:
                fill = theme.ACCENT
            fg = theme.TEXT_ON_ACCENT
        else:
            fill, fg = theme.SURFACE_3, theme.TEXT_FAINT
        pad = 1
        self.create_oval(pad, pad, self.d - pad, self.d - pad, fill=fill, outline="")
        cx, cy = self.d / 2, self.d / 2
        r = 7.2
        self.create_polygon(
            cx - r, cy + r * 0.75,
            cx, cy - r * 0.9,
            cx + r, cy + r * 0.75,
            cx + r * 0.42, cy + r * 0.75,
            cx + r * 0.42, cy + r,
            cx - r * 0.42, cy + r,
            cx - r * 0.42, cy + r * 0.75,
            fill=fg,
            outline="",
        )

    def _on_event(self, event) -> None:
        kind = getattr(event, "type", None)
        if not self._enabled:
            return
        if kind == tk.EventType.Enter:
            self._hover = True
            self.configure(cursor="hand2")
        elif kind == tk.EventType.Leave:
            self._hover = False
            self._pressed = False
        elif kind == tk.EventType.ButtonPress:
            self._pressed = True
        elif kind == tk.EventType.ButtonRelease and self._pressed:
            self._pressed = False
            if self.command:
                self.command()
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #


class Card(tk.Frame):
    """Flat surface with a hairline border."""

    def __init__(self, master, bg: str = theme.SURFACE_2, border: str = theme.BORDER, **kw):
        super().__init__(
            master, bg=bg, highlightbackground=border, highlightthickness=1, bd=0, **kw
        )


class Separator(tk.Frame):
    def __init__(self, master, color: str = theme.BORDER, thickness: int = 1, **kw):
        super().__init__(master, bg=color, height=thickness, **kw)


class Avatar(tk.Canvas):
    """Circular initials badge."""

    def __init__(
        self, master, initials: str = "G", size: int = 30,
        bg: str = theme.ACCENT_DIM, fg: str = theme.ACCENT, **kw
    ):
        super().__init__(
            master,
            width=size,
            height=size,
            bg=kw.pop("background", theme.SURFACE),
            highlightthickness=0,
            bd=0,
            **kw,
        )
        self.size = size
        self._bg = bg
        self._fg = fg
        self._initials = initials
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        self.create_oval(1, 1, self.size - 1, self.size - 1, fill=self._bg, outline="")
        import tkinter.font as tkfont

        font = tkfont.Font(
            family=theme.font_family("sans"), size=max(7, self.size // 3), weight="bold"
        )
        self.create_text(
            self.size / 2, self.size / 2, text=self._initials, fill=self._fg,
            font=font, anchor="center",
        )

    def set_initials(self, initials: str) -> None:
        self._initials = initials
        self._draw()


# --------------------------------------------------------------------------- #
# Scrolling
# --------------------------------------------------------------------------- #


class ScrollableFrame(tk.Frame):
    """A vertically scrolling frame whose content tracks the canvas width.

    ``<MouseWheel>`` is bound on the toplevel (guarded by a hit test) so
    scrolling keeps working for every child added later, including after a
    window resize.
    """

    def __init__(self, master, bg: str = theme.BG, show_bar: bool = False, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        if show_bar:
            self.vsb = tk.Scrollbar(
                self, orient="vertical", command=self.canvas.yview,
                bg=theme.SURFACE, troughcolor=theme.BG, highlightthickness=0, bd=0, width=8,
            )
            self.vsb.pack(side="right", fill="y")
        else:
            self.vsb = None
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._wheel_bound = False

    def _on_scroll(self, first, last):
        if self.vsb is not None:
            self.vsb.set(first, last)
        try:
            self.canvas.yview_moveto(float(first))
        except Exception:  # pragma: no cover - defensive
            pass

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        if event is not None:
            self.canvas.itemconfigure(self._window, width=event.width)
        self._on_inner_configure()

    def bind_wheel(self) -> None:
        if self._wheel_bound:
            return
        top = self.winfo_toplevel()
        try:
            top.bind_all("<MouseWheel>", self._wheel, add="+")
            top.bind_all("<Button-4>", self._wheel, add="+")
            top.bind_all("<Button-5>", self._wheel, add="+")
        except Exception:  # pragma: no cover - defensive
            return
        self._wheel_bound = True

    def _wheel(self, event) -> None:
        if not self._pointer_inside():
            return
        num = getattr(event, "num", None)
        if num == 4:
            units = -3
        elif num == 5:
            units = 3
        else:
            delta = getattr(event, "delta", 0) or 0
            if delta == 0:
                return
            units = -3 if delta > 0 else 3
        try:
            self.canvas.yview_scroll(units, "units")
        except Exception:  # pragma: no cover - defensive
            pass

    def _pointer_inside(self) -> bool:
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            widget = self.winfo_toplevel().winfo_containing(x, y)
        except Exception:  # pragma: no cover - defensive
            return False
        while widget is not None:
            if widget in (self.canvas, self.inner):
                return True
            widget = getattr(widget, "master", None)
        return False

    def scroll_to_bottom(self) -> None:
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def at_bottom(self, tolerance: float = 12.0) -> bool:
        try:
            _top, bottom = self.canvas.yview()
        except Exception:  # pragma: no cover - defensive
            return True
        return bottom >= 1.0 - tolerance / max(1, self.canvas.winfo_height())


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #


class Toast(tk.Frame):
    """Transient status line that removes itself after ``ttl`` ms."""

    def __init__(self, master, text: str = "", kind: str = "info", ttl: int = 6000, **kw):
        bg = kw.pop("background", theme.SURFACE_2)
        super().__init__(master, bg=bg, **kw)
        colors = {
            "info": (theme.TEXT_MUTED, theme.BORDER_2),
            "error": (theme.DANGER, theme.DANGER),
            "success": (theme.SUCCESS, theme.SUCCESS),
            "warn": (theme.WARN, theme.WARN),
        }
        fg, bar = colors.get(kind, colors["info"])
        self.bar = tk.Frame(self, bg=bar, width=3)
        self.bar.pack(side="left", fill="y")
        self.label = tk.Label(
            self, text=text, bg=bg, fg=fg, anchor="w", justify="left",
            font=ui_font(theme.SIZE_SM), padx=10, pady=7, wraplength=420,
        )
        self.label.pack(side="left", fill="both", expand=True)
        self._ttl = ttl
        self._job = None

    def show(self) -> None:
        self.pack(fill="x", padx=16, pady=(0, 8))
        if self._ttl:
            self._job = self.after(self._ttl, self.hide)

    def hide(self) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:  # pragma: no cover - defensive
                pass
            self._job = None
        try:
            self.pack_forget()
        except Exception:  # pragma: no cover - defensive
            pass

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


_FONT_CACHE = {}


def ui_font(size: int, bold: bool = False, mono: bool = False, italic: bool = False):
    import tkinter.font as tkfont

    key = (size, bold, mono, italic)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = tkfont.Font(
            family=theme.font_family("mono" if mono else "sans"),
            size=size,
            weight="bold" if bold else "normal",
            slant="italic" if italic else "roman",
        )
    return _FONT_CACHE[key]
