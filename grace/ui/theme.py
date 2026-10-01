"""Golden-green dark theme tokens.

Palette intent (from the brief): a very dark green/black canvas, a
golden-green/lime accent, muted olive secondary text and warm white primary
text.  No neon, no heavy gradients.
"""

from __future__ import annotations

from typing import Dict, Tuple

# --------------------------------------------------------------------------- #
# Colour tokens
# --------------------------------------------------------------------------- #

BG = "#04080A"            # app canvas - very dark green/black
SURFACE = "#080F0C"       # sidebar
SURFACE_2 = "#0C1512"     # cards, composer
SURFACE_3 = "#111B16"     # hovered cards
SURFACE_4 = "#16221C"     # pressed / selected

BORDER = "#182720"
BORDER_2 = "#23382D"
BORDER_3 = "#2E4636"

ACCENT = "#A9CE4B"        # golden-green / lime
ACCENT_HOVER = "#BCDD63"
ACCENT_ACTIVE = "#93B93C"
ACCENT_DIM = "#33411C"
ACCENT_WASH = "#131C0D"

TEXT = "#EDF4E6"          # warm white
TEXT_MUTED = "#A0B296"    # muted olive
TEXT_FAINT = "#6F8067"
TEXT_ON_ACCENT = "#0A1206"

DANGER = "#E0714A"
DANGER_WASH = "#2A150E"
WARN = "#D8B45A"
SUCCESS = "#7FBF5A"

BUBBLE_USER = "#16240F"
BUBBLE_USER_BORDER = "#2C3F1B"
CODE_BG = "#060C09"
CODE_HEADER = "#0C1410"
CODE_BORDER = "#1B2C22"

# Markdown inline styles
CODE_TEXT = "#CFE3B4"
LINK_COLOR = "#8FD1E0"

#: Semantic aliases used by the widgets.
SELECTION = SURFACE_4


# --------------------------------------------------------------------------- #
# Typography
# --------------------------------------------------------------------------- #

#: Preferred families, in order.  Resolved against what Tk actually has.
SANS_STACK: Tuple[str, ...] = (
    "Inter",
    "Segoe UI Variable Text",
    "Segoe UI",
    "Ubuntu",
    "Cantarell",
    "Noto Sans",
    "DejaVu Sans",
    "Helvetica",
)
MONO_STACK: Tuple[str, ...] = (
    "JetBrains Mono",
    "Cascadia Code",
    "Consolas",
    "Ubuntu Mono",
    "DejaVu Sans Mono",
    "Courier New",
)

_FONT_CACHE: Dict[str, Tuple[str, bool]] = {}


def resolve_fonts(root=None) -> None:
    """Populate the font cache.  Safe to call before a Tk root exists."""
    if _FONT_CACHE:
        return
    available: set = set()
    if root is not None:
        try:
            import tkinter.font as tkfont

            available = set(tkfont.families(root))
        except Exception:  # pragma: no cover - defensive
            available = set()

    def pick(stack: Tuple[str, ...]) -> Tuple[str, bool]:
        for name in stack:
            if not available or name in available:
                return name, True
        return stack[-1], False

    _FONT_CACHE["sans"] = pick(SANS_STACK)
    _FONT_CACHE["mono"] = pick(MONO_STACK)


def font_family(kind: str = "sans") -> str:
    if not _FONT_CACHE:
        return SANS_STACK[-1] if kind == "sans" else MONO_STACK[-1]
    return _FONT_CACHE.get(kind, _FONT_CACHE["sans"])[0]


# --------------------------------------------------------------------------- #
# Type scale (points)
# --------------------------------------------------------------------------- #

SIZE_XS = 8
SIZE_SM = 9
SIZE_BASE = 10
SIZE_MD = 11
SIZE_LG = 13
SIZE_XL = 17
SIZE_2XL = 22

# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #

RADIUS = 10
RADIUS_SM = 7
RADIUS_PILL = 999

SIDEBAR_WIDTH = 268
COMPOSER_MAX_HEIGHT = 190

#: Vertical rhythm inside the message list.
MSG_GAP = 18
MSG_PAD_X = 22
MSG_PAD_Y = 14


def cairo_round(widget, radius: int = RADIUS):
    """Placeholder kept for readability; Tk has no rounded frames natively."""
    return radius
