"""Server-Sent Events parsing for ``POST /api/ai/grace/respond``.

The parser is deliberately strict about the SSE *framing* rules and lenient
about the JSON inside a frame:

* ``data:`` lines accumulate and are joined with ``\\n`` (multi-line data);
* ``event:``, ``id:`` and ``retry:`` are captured but not required;
* lines starting with ``:`` are comments/heartbeats and are skipped;
* a blank line dispatches the buffered event;
* a frame whose payload is not valid JSON is reported as ``malformed`` rather
  than aborting the stream;
* ``data: [DONE]`` sets ``done`` and ends iteration.

Line splitting is done here (rather than with ``Response.iter_lines``) so that
partial UTF-8 sequences and ``\\r\\n`` terminators cannot desynchronise the
frame boundaries.
"""

from __future__ import annotations

import codecs
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, List, Optional

DONE_SENTINEL = "[DONE]"


@dataclass
class SSEEvent:
    """One dispatched SSE frame."""

    data: str = ""
    event: str = "message"
    id: Optional[str] = None
    retry: Optional[int] = None
    raw: str = ""

    @property
    def is_done(self) -> bool:
        return self.data.strip() == DONE_SENTINEL

    def json(self) -> Any:
        """Parsed payload, or ``None`` when the frame is not valid JSON."""
        if not self.data:
            return None
        try:
            return json.loads(self.data)
        except (ValueError, TypeError):
            return None


@dataclass
class SSEStats:
    """Counters used by the debug log and the tests."""

    events: int = 0
    chunks: int = 0
    statuses: int = 0
    malformed: int = 0
    comments: int = 0
    done: bool = False
    truncated: bool = False
    fields: List[str] = field(default_factory=list)


class SSEParser:
    """Incremental SSE decoder fed with arbitrary byte chunks."""

    def __init__(self) -> None:
        self._buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._data: List[str] = []
        self._event = "message"
        self._id: Optional[str] = None
        self._retry: Optional[int] = None
        self._has_fields = False
        self.stats = SSEStats()

    # ------------------------------------------------------------------ #
    def feed(self, chunk: bytes) -> List[SSEEvent]:
        """Consume ``chunk`` and return every event it completed."""
        if isinstance(chunk, (bytes, bytearray)):
            # Incremental decoding so a multi-byte character split across two
            # network chunks is not replaced with U+FFFD.
            self._buffer += self._decoder.decode(bytes(chunk))
        else:
            self._buffer += str(chunk)
        events: List[SSEEvent] = []
        while True:
            idx = self._find_newline()
            if idx is None:
                break
            line = self._buffer[:idx]
            self._buffer = self._buffer[idx + self._newline_len(idx):]
            event = self._handle_line(line)
            if event is not None:
                events.append(event)
        return events

    def flush(self) -> List[SSEEvent]:
        """Dispatch a trailing frame that was never blank-line terminated."""
        events: List[SSEEvent] = []
        if self._buffer:
            line, self._buffer = self._buffer, ""
            event = self._handle_line(line)
            if event is not None:
                events.append(event)
        trailing = self._dispatch()
        if trailing is not None:
            events.append(trailing)
        return events

    # ------------------------------------------------------------------ #
    def _find_newline(self) -> Optional[int]:
        lf = self._buffer.find("\n")
        cr = self._buffer.find("\r")
        if lf == -1 and cr == -1:
            return None
        if lf == -1:
            return cr
        if cr == -1:
            return lf
        return min(lf, cr)

    def _newline_len(self, idx: int) -> int:
        if self._buffer[idx] == "\r" and idx + 1 < len(self._buffer):
            if self._buffer[idx + 1] == "\n":
                return 2
        return 1

    def _handle_line(self, line: str) -> Optional[SSEEvent]:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            self.stats.comments += 1
            return None

        field, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if not sep:
            field, value = line, ""

        if field == "data":
            self._data.append(value)
            self._has_fields = True
        elif field == "event":
            self._event = value
            self._has_fields = True
        elif field == "id":
            self._id = value
            self._has_fields = True
        elif field == "retry":
            try:
                self._retry = int(value)
            except ValueError:
                pass
            self._has_fields = True
        # Unknown fields are ignored, per the SSE specification.
        return None

    def _dispatch(self) -> Optional[SSEEvent]:
        if not self._has_fields:
            # Blank line with nothing buffered: keep-alive noise.
            self._reset()
            return None
        data = "\n".join(self._data)
        event = SSEEvent(
            data=data,
            event=self._event or "message",
            id=self._id,
            retry=self._retry,
            raw=data,
        )
        self._reset()
        self.stats.events += 1
        if event.is_done:
            self.stats.done = True
        return event

    def _reset(self) -> None:
        self._data = []
        self._event = "message"
        self._id = None
        self._retry = None
        self._has_fields = False


def parse_stream(chunks: Iterable[bytes]) -> Iterator[SSEEvent]:
    """Convenience generator: feed an iterable of byte chunks."""
    parser = SSEParser()
    for chunk in chunks:
        for event in parser.feed(chunk):
            yield event
    for event in parser.flush():
        yield event


def parse_text(text: str) -> List[SSEEvent]:
    """Parse a complete SSE document (handy in tests)."""
    return list(parse_stream([text.encode("utf-8")]))


def classify(event: SSEEvent) -> str:
    """Bucket an event for logging: ``done``/``status``/``chunk``/``other``."""
    if event.is_done:
        return "done"
    payload = event.json()
    if isinstance(payload, dict):
        kind = payload.get("type")
        if kind == "chunk":
            return "chunk"
        if kind == "status":
            return "status"
        if kind == "done":
            return "done"
        return f"other:{kind}"
    return "malformed"
