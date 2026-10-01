"""The Grace mode registry."""

from __future__ import annotations

from grace import config, modes


def test_seven_modes_are_exposed():
    assert len(modes.ALL_MODES) == 7


def test_mode_labels_match_the_shipped_selector():
    labels = [m.short_label for m in modes.ALL_MODES]
    assert labels == [
        "Normal",
        "Normal · Thinking",
        "Medium",
        "Medium · Thinking",
        "Ultra",
        "Ultra · Thinking",
        "Deep Research",  # deep research does not repeat "Thinking"
    ]
    assert len(labels) == len(modes.ALL_MODES)


def test_default_mode_is_the_verified_pair():
    assert modes.default() is modes.NORMAL
    assert modes.default().verified is True
    assert modes.default().payload() == {"mode": "normal", "effort": "instant"}
    assert modes.default().payload() == {
        "mode": config.DEFAULT_MODE,
        "effort": config.DEFAULT_EFFORT,
    }


def test_only_normal_is_marked_verified():
    assert modes.verified_modes() == [modes.NORMAL]
    assert len(modes.unverified_modes()) == len(modes.ALL_MODES) - 1


def test_thinking_modes_carry_the_thinking_flag():
    thinking = [m for m in modes.ALL_MODES if m.thinking]
    assert len(thinking) == 4
    assert all(m.effort == "thinking" for m in thinking)


def test_deep_research_is_slow():
    assert modes.DEEP_RESEARCH.slow is True
    assert modes.DEEP_RESEARCH.mode == "deep_research"


def test_payload_round_trip():
    for mode in modes.ALL_MODES:
        payload = mode.payload()
        assert set(payload) == {"mode", "effort"}
        assert modes.from_payload(payload["mode"], payload["effort"]) is mode


def test_unknown_pair_has_no_registry_entry():
    assert modes.from_payload("turbo", "max") is None


def test_lookup_falls_back_to_normal():
    assert modes.get("nope") is modes.NORMAL
    assert modes.get("ultra") is modes.ULTRA


def test_label_for_arbitrary_pairs():
    assert modes.label_for("normal", "instant") == "Normal"
    assert modes.label_for("ultra", "thinking") == "Ultra · Thinking"
    assert modes.label_for("mystery", "instant") == "Mystery"
    assert modes.label_for("deep_research", "instant") == "Deep Research"


def test_every_mode_has_a_hint():
    assert all(m.hint for m in modes.ALL_MODES)


def test_mode_keys_are_unique():
    keys = [m.key for m in modes.ALL_MODES]
    assert len(keys) == len(set(keys))
