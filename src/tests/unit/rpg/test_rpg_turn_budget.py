"""The per-user turn ceiling's message, retry time and switch (RQ-8.2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.apps.rpg.session import turn_budget


def test_the_refusal_says_how_many_turns_were_played_and_when_play_resumes() -> None:
    exceeded = turn_budget.TurnBudgetExceeded(limit=600, used=600, retry_after_seconds=61)

    assert str(exceeded) == (
        "You have played 600 turns in the last hour; the limit is 600. You can play again in about 2 minutes."
    )
    assert "about 1 minute." in str(turn_budget.TurnBudgetExceeded(limit=5, used=5, retry_after_seconds=30))


def test_play_resumes_when_the_oldest_turn_in_the_window_leaves_it() -> None:
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

    assert turn_budget._retry_after(now - timedelta(minutes=50), now=now) == 601
    assert turn_budget._retry_after((now - timedelta(minutes=50)).replace(tzinfo=None), now=now) == 601
    assert turn_budget._retry_after(None, now=now) == turn_budget.WINDOW_SECONDS


def test_the_ceiling_defaults_on_and_zero_turns_it_off(monkeypatch) -> None:
    monkeypatch.delenv(turn_budget.TURNS_PER_HOUR_ENV, raising=False)
    assert turn_budget.turns_per_hour() == turn_budget.DEFAULT_TURNS_PER_HOUR

    monkeypatch.setenv(turn_budget.TURNS_PER_HOUR_ENV, "0")
    assert turn_budget.turns_per_hour() == 0
    turn_budget.require_turn_budget()  # off: never queries, never refuses
