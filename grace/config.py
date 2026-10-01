"""Central configuration for the Aero Grace desktop client.

Every value that touches the network lives here so the exact contract the
client speaks can be audited in one place.

Provenance of each constant is recorded in ``_PROVENANCE`` and surfaced by
``contract_report()`` so the shipped binary can never silently drift away
from the endpoints that were actually observed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #

#: Origin of the Aero REST API.  HTTPS only - there is no plaintext fallback.
API_ORIGIN: str = os.environ.get("AERO_API_ORIGIN", "https://api.aryankaushik.space")

#: Every Aero REST route is mounted under this prefix.
API_PREFIX: str = "/api"

#: Timeouts (seconds).
CONNECT_TIMEOUT: float = float(os.environ.get("AERO_CONNECT_TIMEOUT", "15"))
#: Read timeout for the SSE stream.  Deep Research answers can take minutes.
READ_TIMEOUT: float = float(os.environ.get("AERO_READ_TIMEOUT", "600"))

#: User-Agent sent with every request.
USER_AGENT: str = f"AeroGraceDesktop/{__import__('grace').__version__}"

# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

#: ``POST`` - body ``{"identifier": str, "password": str}``.
PATH_AUTH_LOGIN = "/auth/login"

#: ``POST`` - second leg of the OTP login challenge.
#: UNVERIFIED: the live contract was not observable from this environment.
#: Overridable with ``AERO_OTP_VERIFY_PATH``.
PATH_AUTH_OTP_VERIFY = os.environ.get(
    "AERO_OTP_VERIFY_PATH", "/auth/login/verify-otp"
)

#: ``GET`` - returns the account's Grace conversations.
PATH_GRACE_CHATS = "/ai/grace/chats"

#: ``POST`` - body ``{"message": str}`` -> ``{"title": str}``.
PATH_GRACE_TITLE = "/ai/grace/generate-title"

#: ``POST`` - Server-Sent Events answer stream.
PATH_GRACE_RESPOND = "/ai/grace/respond"

#: ``POST`` - multipart attachment upload used by the composer.
#: UNVERIFIED: the browser request for "Grace -> Attach file" was not
#: observable from this environment.  Overridable with
#: ``AERO_UPLOAD_PATH`` / ``AERO_UPLOAD_FIELD``.
PATH_UPLOAD = os.environ.get("AERO_UPLOAD_PATH", "/ai/grace/upload")
UPLOAD_FIELD = os.environ.get("AERO_UPLOAD_FIELD", "file")

#: Field name used to hand uploaded references back to ``/respond``.
#: UNVERIFIED: the documented request shape carries no attachment field.
PATH_GRACE_ATTACH_FIELD = os.environ.get("AERO_ATTACH_FIELD", "attachments")

_PROVENANCE: Dict[str, str] = {
    "PATH_AUTH_LOGIN": "documented",
    "PATH_GRACE_CHATS": "documented",
    "PATH_GRACE_TITLE": "documented",
    "PATH_GRACE_RESPOND": "documented",
    "PATH_AUTH_OTP_VERIFY": "inferred",
    "PATH_UPLOAD": "inferred",
    "UPLOAD_FIELD": "inferred",
    "PATH_GRACE_ATTACH_FIELD": "inferred",
}


def contract_report() -> List[Tuple[str, str, str]]:
    """Return ``(name, value, provenance)`` for every endpoint constant."""
    rows: List[Tuple[str, str, str]] = []
    for name, value in sorted(globals().items()):
        if not name.startswith(("PATH_", "UPLOAD_")) or name.startswith("_"):
            continue
        if not isinstance(value, str):
            continue
        rows.append((name, value, _PROVENANCE.get(name, "documented")))
    return rows


def url(path: str) -> str:
    """Join ``path`` onto the API origin + prefix."""
    return f"{API_ORIGIN}{API_PREFIX}{path}"


# --------------------------------------------------------------------------- #
# Grace request defaults (verified subset of the observed contract)
# --------------------------------------------------------------------------- #

#: Capability identifiers that were actually observed on the wire.
DEFAULT_CAPABILITIES: Tuple[str, ...] = ("workspace_v2", "ask_user", "drawings_v1")

#: Baseline mode/effort pair that is known to be accepted.
DEFAULT_MODE = "normal"
DEFAULT_EFFORT = "instant"


# --------------------------------------------------------------------------- #
# Attachment policy
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AttachmentPolicy:
    """File rules for the composer's attachment picker.

    The extension/MIME table mirrors what Aero Drive can preview (image,
    video, audio, pdf, text/code) plus archives, which is the closest
    observable evidence of what Aero's storage layer accepts.
    """

    max_bytes: int = 25 * 1024 * 1024
    max_count: int = 10
    extensions: Tuple[str, ...] = (
        # text / code
        ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv",
        ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".env",
        ".xml", ".html", ".htm", ".css", ".scss", ".less",
        ".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
        ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".cs", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".sql", ".r",
        ".jl", ".lua", ".pl", ".dart", ".vue", ".svelte", ".graphql",
        ".gql", ".proto", ".tf", ".gitignore", ".editorconfig",
        # documents
        ".pdf", ".rtf", ".tex",
        # images
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif",
        ".heic", ".heif", ".tiff", ".tif", ".ico",
        # audio / video
        ".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac", ".opus",
        ".weba", ".mid", ".midi",
        ".mp4", ".m4v", ".webm", ".mov", ".avi", ".mkv", ".mpeg", ".mpg",
        ".wmv", ".flv", ".3gp",
        # archives
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz",
    )

    #: Extensions deliberately *not* offered even though Drive stores them.
    blocked_extensions: Tuple[str, ...] = (
        ".exe", ".dll", ".so", ".dylib", ".bin", ".msi", ".app", ".deb",
        ".rpm", ".apk", ".ipa", ".jar", ".war", ".class", ".o", ".obj",
        ".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".iso", ".dmg",
        ".vhd", ".vmdk", ".reg", ".scr", ".cpl", ".hta", ".lnk", ".ps1",
        ".ps1xml", ".bat", ".cmd", ".sh", ".bash", ".zsh", ".fish", ".vbs",
        ".js", ".jse", ".wsf", ".run", ".command", ".gadget", ".appimage",
    )


DEFAULT_ATTACHMENT_POLICY = AttachmentPolicy()


# --------------------------------------------------------------------------- #
# Window / UX
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class WindowConfig:
    title: str = "Aero · Grace"
    min_width: int = 940
    min_height: int = 620
    default_width: int = 1360
    default_height: int = 860
    sidebar_width: int = 268


DEFAULT_WINDOW = WindowConfig()


@dataclass
class Settings:
    """Runtime-tunable behaviour.

    ``send_attachments`` gates whether uploaded references are added to the
    ``/respond`` payload.  It defaults to ``True`` because the whole point of
    the composer's attach button is to put the file in front of Grace, but it
    is a single switch so the behaviour can be disabled if the live API turns
    out to reject the field.
    """

    send_attachments: bool = True
    include_history: bool = True
    stream: bool = True
    #: Extra keys appended to every history entry.  Kept empty by default so
    #: the payload stays at the minimal ``{"role", "content"}`` shape.
    history_extra_fields: Tuple[str, ...] = field(default_factory=tuple)


DEFAULT_SETTINGS = Settings()
