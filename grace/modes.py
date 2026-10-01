"""Grace response modes.

The observed ``/respond`` payload carries two orthogonal knobs::

    {"mode": "normal", "effort": "instant", ...}

and the SSE ``done`` event echoes them back as ``tier`` / ``thinking`` /
``effort``.  The composer in the real Aero web client renders the pair as a
single label - the screenshot of the shipped Grace UI reads
``Ultra · Thinking`` - which is what the registry below reproduces.

``mode``  the reasoning tier  -> echoed back as ``tier``
``effort`` how hard it thinks -> echoed back as ``effort``, and drives the
          boolean ``thinking`` flag in the response.

Only ``("normal", "instant")`` is a documented, verified pair.  Every other
row is *inferred from the visible mode selector* and is marked as such so the
UI can label it honestly and the client can fall back if the server rejects
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class GraceMode:
    key: str
    label: str
    mode: str
    effort: str
    thinking: bool
    hint: str = ""
    verified: bool = False
    #: Overrides the auto-generated selector label when set.
    selector_label: str = ""
    #: Modes that think for a long time need a longer read timeout.
    slow: bool = False

    @property
    def short_label(self) -> str:
        """Compact label used inside the composer button."""
        if self.selector_label:
            return self.selector_label
        if self.thinking:
            return f"{self.label} · Thinking"
        return self.label

    def payload(self) -> Dict[str, str]:
        """The two request fields this mode contributes."""
        return {"mode": self.mode, "effort": self.effort}


NORMAL = GraceMode(
    key="normal",
    label="Normal",
    mode="normal",
    effort="instant",
    thinking=False,
    hint="Fastest answers for everyday questions",
    verified=True,
)

NORMAL_THINKING = GraceMode(
    key="normal-thinking",
    label="Normal",
    mode="normal",
    effort="thinking",
    thinking=True,
    hint="Normal speed with a reasoning pass first",
)

MEDIUM = GraceMode(
    key="medium",
    label="Medium",
    mode="medium",
    effort="instant",
    thinking=False,
    hint="Balanced depth and speed",
)

MEDIUM_THINKING = GraceMode(
    key="medium-thinking",
    label="Medium",
    mode="medium",
    effort="thinking",
    thinking=True,
    hint="Balanced depth with a reasoning pass first",
)

ULTRA = GraceMode(
    key="ultra",
    label="Ultra",
    mode="ultra",
    effort="instant",
    thinking=False,
    hint="Maximum capability, fastest it can manage",
)

ULTRA_THINKING = GraceMode(
    key="ultra-thinking",
    label="Ultra",
    mode="ultra",
    effort="thinking",
    thinking=True,
    hint="Deepest reasoning — slowest and most expensive",
    slow=True,
)

DEEP_RESEARCH = GraceMode(
    key="deep-research",
    label="Deep Research",
    mode="deep_research",
    effort="thinking",
    thinking=True,
    hint="Multi-step research with sources — takes minutes",
    selector_label="Deep Research",
    slow=True,
)

#: Order shown in the composer's mode menu.
ALL_MODES: Tuple[GraceMode, ...] = (
    NORMAL,
    NORMAL_THINKING,
    MEDIUM,
    MEDIUM_THINKING,
    ULTRA,
    ULTRA_THINKING,
    DEEP_RESEARCH,
)

_BY_KEY: Dict[str, GraceMode] = {m.key: m for m in ALL_MODES}
_DEFAULT = NORMAL


def default() -> GraceMode:
    return _DEFAULT


def get(key: str) -> GraceMode:
    """Look up a mode by key, falling back to the verified default."""
    return _BY_KEY.get(key, _DEFAULT)


def from_payload(mode: str, effort: str) -> Optional[GraceMode]:
    """Find the registry row matching a ``mode``/``effort`` pair."""
    for candidate in ALL_MODES:
        if candidate.mode == mode and candidate.effort == effort:
            return candidate
    return None


def label_for(mode: str, effort: str) -> str:
    """Human label for an arbitrary pair (used to render server echoes)."""
    found = from_payload(mode, effort)
    if found:
        return found.short_label
    tier = (mode or "normal").replace("_", " ").title()
    if effort and effort != "instant":
        return f"{tier} · {effort.title()}"
    return tier


def verified_modes() -> List[GraceMode]:
    return [m for m in ALL_MODES if m.verified]


def unverified_modes() -> List[GraceMode]:
    return [m for m in ALL_MODES if not m.verified]


def iter_keys() -> Iterable[str]:
    return _BY_KEY.keys()
