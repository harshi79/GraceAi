"""Value objects shared by the API layer, the controller and the UI."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"


def new_id(prefix: str = "") -> str:
    """Opaque client-side identifier (uuid4 hex, optionally prefixed)."""
    return f"{prefix}{uuid.uuid4().hex}" if prefix else uuid.uuid4().hex


def now_iso() -> str:
    """UTC timestamp in the shape Aero uses elsewhere (``...Z``)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class User:
    """Authenticated Aero account (subset of the login response)."""

    id: str = ""
    username: str = ""
    full_name: str = ""
    email: str = ""
    profile_pic: str = ""
    avatar_version: int = 0
    avatar_has_image: bool = False
    joined_at: str = ""
    last_username_change_at: str = ""
    login_otp_enabled: bool = False
    plan: str = ""
    apex_badge: bool = False
    requires_date_of_birth: bool = False
    preferences: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_login(cls, data: Dict[str, Any]) -> "User":
        prefs = data.get("preferences")
        return cls(
            id=str(data.get("_id") or data.get("id") or ""),
            username=str(data.get("username") or ""),
            full_name=str(data.get("fullName") or data.get("full_name") or ""),
            email=str(data.get("email") or ""),
            profile_pic=str(data.get("profilePic") or data.get("profile_pic") or ""),
            avatar_version=int(data.get("avatarVersion") or 0),
            avatar_has_image=bool(data.get("avatarHasImage")),
            joined_at=str(data.get("joinedAt") or ""),
            last_username_change_at=str(data.get("lastUsernameChangeAt") or ""),
            login_otp_enabled=bool(data.get("loginOtpEnabled")),
            plan=str(data.get("plan") or ""),
            apex_badge=bool(data.get("apexBadge")),
            requires_date_of_birth=bool(data.get("requiresDateOfBirth")),
            preferences=prefs if isinstance(prefs, dict) else {},
        )

    @property
    def display_name(self) -> str:
        return self.full_name or self.username or "Aero user"

    @property
    def handle(self) -> str:
        return f"@{self.username}" if self.username else ""


@dataclass
class Attachment:
    """A file the user attached to a pending message."""

    id: str
    path: str
    name: str
    size: int
    mime: str
    #: ``pending`` | ``uploading`` | ``uploaded`` | ``failed``
    state: str = "pending"
    progress: float = 0.0
    error: str = ""
    remote_id: str = ""
    attempts: int = 0

    @property
    def ready(self) -> bool:
        return self.state == "uploaded" and bool(self.remote_id)


@dataclass
class Message:
    """One turn of the conversation."""

    id: str
    role: str
    content: str
    at: str = field(default_factory=now_iso)
    attachments: List[Attachment] = field(default_factory=list)
    #: Set for assistant turns, straight from the SSE ``done`` event.
    meta: Dict[str, Any] = field(default_factory=dict)
    streaming: bool = False
    error: bool = False

    def to_history_entry(self, extra: tuple = ()) -> Dict[str, Any]:
        """Serialise for the ``conversationHistory`` request field."""
        entry: Dict[str, Any] = {"role": self.role, "content": self.content}
        for key in extra:
            if key == "id":
                entry["id"] = self.id
            elif key == "createdAt":
                entry["createdAt"] = self.at
        return entry


@dataclass
class Conversation:
    """The single active Grace conversation for this client session."""

    id: str
    title: str = "New conversation"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    #: ``local`` until the server acknowledges the id, then ``server``.
    origin: str = "local"
    title_generated: bool = False
    messages: List[Message] = field(default_factory=list)

    @property
    def user_messages(self) -> List[Message]:
        return [m for m in self.messages if m.role == ROLE_USER]

    @property
    def assistant_messages(self) -> List[Message]:
        return [m for m in self.messages if m.role == ROLE_ASSISTANT]

    def history(self, extra: tuple = ()) -> List[Dict[str, Any]]:
        """History payload sent with every ``/respond`` request."""
        return [m.to_history_entry(extra) for m in self.messages]


@dataclass
class Credits:
    """Grace credit balance, taken from the SSE ``done`` event."""

    remaining: Optional[float] = None
    used: Optional[float] = None
    tier: str = ""
    thinking: Optional[bool] = None
    effort: str = ""

    @property
    def label(self) -> str:
        if self.remaining is None:
            return ""
        value = f"{self.remaining:g}"
        if self.tier:
            return f"{value} credits left · {self.tier}"
        return f"{value} credits left"


@dataclass
class StreamResult:
    """Outcome of one ``/respond`` call."""

    full_content: str = ""
    credits_used: Optional[float] = None
    remaining_credits: Optional[float] = None
    tier: str = ""
    thinking: Optional[bool] = None
    effort: str = ""
    conversation_id: str = ""
    message_id: str = ""
    statuses: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
