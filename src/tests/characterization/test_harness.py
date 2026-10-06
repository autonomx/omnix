from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from tests.characterization import harness
from tests.characterization.fakes import FakeLLMProvider, FakeMarketData, FakeTTS, prompt_digest


def test_normalize_removes_identifiers_times_and_durations() -> None:
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")

    result = harness.normalize(
        {
            "session_id": f"chat:{first.hex}",
            "created_at": "2026-09-29T12:00:00+00:00",
            "duration_ms": 93.123456789,
            "score": 1.23456789,
            "unordered": {"z", "a"},
            "messages": [{"id": f"msg:{first.hex}"}, {"id": f"msg:{second.hex}"}],
        }
    )

    assert result == {
        "session_id": "chat:<uuid:1>",
        "created_at": "<timestamp>",
        "duration_ms": "<duration>",
        "score": 1.234568,
        "unordered": ["a", "z"],
        "messages": [{"id": "msg:<uuid:1>"}, {"id": "msg:<uuid:2>"}],
    }


def test_capture_requires_a_checked_in_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "GOLDEN_DIR", tmp_path)
    monkeypatch.delenv("OMNIX_UPDATE_GOLDEN", raising=False)

    with pytest.raises(AssertionError, match="missing characterization golden"):
        harness.capture("missing-scenario", lambda: {"ok": True})


def test_capture_updates_only_with_explicit_environment_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "GOLDEN_DIR", tmp_path)
    monkeypatch.setenv("OMNIX_UPDATE_GOLDEN", "1")

    captured = harness.capture("new-scenario", lambda: {"result": {"b", "a"}})

    assert captured == {"result": ["a", "b"]}
    assert (tmp_path / "new-scenario.json").read_text(encoding="utf-8") == (
        '{\n  "result": [\n    "a",\n    "b"\n  ]\n}\n'
    )
    monkeypatch.delenv("OMNIX_UPDATE_GOLDEN")
    assert harness.capture("new-scenario", lambda: {"result": {"a", "b"}}) == captured


def test_capture_rejects_path_like_scenario_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "GOLDEN_DIR", tmp_path)

    with pytest.raises(ValueError, match="invalid characterization scenario name"):
        harness.capture("../outside", lambda: {})


def test_deterministic_provider_fakes_use_fixed_inputs() -> None:
    prompt = [{"role": "user", "content": "hello"}]
    digest = prompt_digest(prompt)
    provider = FakeLLMProvider({digest: ("Hello", " there.")})
    streamed = list(provider.chat_completion(messages=prompt, model="fixture", stream=True))
    market = FakeMarketData(
        {"OMNX": ({"open": 1.0, "close": 1.5}, {"open": 1.5, "close": 2.0})}
    )
    tts = FakeTTS(frame_count=2, frame_bytes=4)

    assert [chunk.content for chunk in streamed] == ["Hello", " there."]
    assert provider.calls[0]["prompt_hash"] == digest
    assert market.bars("OMNX", limit=1) == ({"open": 1.5, "close": 2.0},)
    assert tts.synthesize("hello") == tts.synthesize("hello")
    assert len(tts.synthesize("hello")) == 2
