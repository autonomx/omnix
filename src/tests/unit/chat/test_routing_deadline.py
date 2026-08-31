from __future__ import annotations

from time import monotonic
from types import SimpleNamespace

from app.chat.routing_deadline import provider_turn_deadline, remaining_turn_seconds


def test_provider_turn_deadline_uses_configured_provider_timeout(monkeypatch) -> None:
    import app.shared as shared

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda _provider_id: SimpleNamespace(config=SimpleNamespace(timeout=12)),
    )
    started = monotonic()

    deadline = provider_turn_deadline("llm:chatgpt_codex")

    assert deadline is not None
    assert started + 11.5 <= deadline <= started + 12.5
    remaining = remaining_turn_seconds(deadline)
    assert remaining is not None and 0 < remaining <= 12


def test_existing_deadline_is_preserved_without_provider_lookup(monkeypatch) -> None:
    import app.shared as shared

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda _provider_id: (_ for _ in ()).throw(
            AssertionError("existing request deadline should be authoritative")
        ),
    )
    deadline = monotonic() + 3

    assert provider_turn_deadline("chatgpt_codex", existing_deadline_at=deadline) == deadline
