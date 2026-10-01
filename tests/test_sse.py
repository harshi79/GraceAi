"""SSE framing: multi-line data, comments, [DONE], malformed JSON, splits."""

from __future__ import annotations

from grace.sse import SSEParser, classify, parse_text


def test_single_event():
    events = parse_text('data: {"type":"chunk","content":"hi"}\n\n')
    assert len(events) == 1
    assert events[0].json() == {"type": "chunk", "content": "hi"}


def test_multiple_events_in_one_chunk():
    text = 'data: {"a":1}\n\ndata: {"b":2}\n\n'
    events = parse_text(text)
    assert [e.json() for e in events] == [{"a": 1}, {"b": 2}]


def test_done_sentinel():
    events = parse_text("data: [DONE]\n\n")
    assert len(events) == 1
    assert events[0].is_done
    assert events[0].json() is None


def test_multiline_data_is_joined_with_newline():
    events = parse_text("data: line one\ndata: line two\n\n")
    assert events[0].data == "line one\nline two"


def test_comments_are_skipped():
    events = parse_text(": keep-alive\n\ndata: {\"x\":1}\n\n")
    assert len(events) == 1
    assert events[0].json() == {"x": 1}


def test_named_event_and_id_and_retry():
    events = parse_text("event: chunk\nid: 7\nretry: 100\ndata: {\"x\":1}\n\n")
    assert events[0].event == "chunk"
    assert events[0].id == "7"
    assert events[0].retry == 100


def test_malformed_json_is_reported_not_raised():
    events = parse_text("data: {not json\n\n")
    assert len(events) == 1
    assert events[0].json() is None
    assert classify(events[0]) == "malformed"


def test_crlf_terminators():
    events = parse_text('data: {"a":1}\r\n\r\n')
    assert len(events) == 1
    assert events[0].json() == {"a": 1}


def test_no_trailing_blank_line():
    events = parse_text('data: {"a":1}\n')
    assert len(events) == 1
    assert events[0].json() == {"a": 1}


def test_blank_lines_between_events():
    events = parse_text('\n\ndata: {"a":1}\n\n\n\n')
    assert len(events) == 1


def test_chunk_split_across_feed_calls():
    parser = SSEParser()
    out = []
    for piece in (b'data: {"type":"ch', b'unk","content":"ab', b'c"}\n', b"\n"):
        out.extend(parser.feed(piece))
    assert len(out) == 1
    assert out[0].json()["content"] == "abc"


def test_utf8_split_across_feed_calls():
    parser = SSEParser()
    payload = 'data: {"content":"café"}\n\n'.encode("utf-8")
    out = []
    for i in range(len(payload)):
        out.extend(parser.feed(payload[i:i + 1]))
    assert out[0].json()["content"] == "café"


def test_stats_counters():
    parser = SSEParser()
    text = (
        ": ping\n\n"
        'data: {"type":"status","content":"thinking"}\n\n'
        'data: {"type":"chunk","content":"x"}\n\n'
        'data: {"type":"chunk","content":"y"}\n\n'
        "data: [DONE]\n\n"
    )
    for event in parser.feed(text.encode("utf-8")):
        pass
    assert parser.stats.comments == 1
    assert parser.stats.events == 4
    assert parser.stats.done is True
    assert parser.stats.malformed == 0


def test_classify_helpers():
    parser = SSEParser()
    events = parser.feed(
        b'data: {"type":"chunk","content":"x"}\n\n'
        b'data: {"type":"status","content":"y"}\n\n'
    )
    assert classify(events[0]) == "chunk"
    assert classify(events[1]) == "status"


def test_flush_dispatches_unterminated_frame():
    parser = SSEParser()
    assert parser.feed(b'data: {"a":1}') == []
    events = parser.flush()
    assert len(events) == 1
    assert events[0].json() == {"a": 1}


def test_empty_feed_is_noop():
    parser = SSEParser()
    assert parser.feed(b"") == []
    assert parser.flush() == []


def test_unknown_fields_ignored():
    events = parse_text("foo: bar\ndata: {\"a\":1}\n\n")
    assert events[0].json() == {"a": 1}
