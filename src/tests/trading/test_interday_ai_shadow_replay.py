"""The AI-arm replay harness: an arm can only see what was known at the simulated moment."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "trade" / "run_interday_ai_shadow_replay.py"
_spec = importlib.util.spec_from_file_location("run_interday_ai_shadow_replay", SCRIPT)
assert _spec is not None and _spec.loader is not None
replay = importlib.util.module_from_spec(_spec)
sys.modules["run_interday_ai_shadow_replay"] = replay
_spec.loader.exec_module(replay)

SESSION = date(2026, 11, 6)
ET = replay.ET
UTC = timezone.utc
INSTRUMENT = "equity:US:TEST"


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(SESSION, time(hour, minute, second), tzinfo=ET).astimezone(UTC)


def _row(start: datetime, close: float = 10.0, volume: int = 1000) -> dict:
    return {"t": replay.utc_iso(start), "o": close, "h": close + 0.1, "l": close - 0.1, "c": close, "v": volume, "vw": close}


class _Archive:
    def __init__(self) -> None:
        self.asked: list[dict] = []

    def quote(self, symbol, *, after=None, before=None):
        self.asked.append({"after": after, "before": before})
        quoted_at = after + timedelta(seconds=2) if after is not None else before - timedelta(seconds=2)
        return {"t": replay.utc_iso(quoted_at), "bp": 9.99, "ap": 10.01, "bs": 100, "as": 100}


def _market(clock_at: datetime, archive=None):
    clock = replay.SimClock(clock_at)
    clock.now = lambda: clock_at
    tape = replay.build_minute_tape("TEST", INSTRUMENT, [], session=SESSION, previous_close=Decimal("10"))
    return replay.ReplayMarket(
        clock=clock, archive=archive or _Archive(), tapes={INSTRUMENT: tape}, session=SESSION,
        bindings={INSTRUMENT: "replay:TEST"}, symbols={INSTRUMENT: "TEST"},
    )


def test_the_cohort_uses_only_bars_finished_by_the_scan_and_skips_illiquid_names() -> None:
    cutoff = _at(9, 15)
    closes = {"LATE": Decimal("1"), "SEEN": Decimal("1"), "THIN": Decimal("1")}
    bars = {
        "LATE": [_row(_at(9, 0), 1.1, 500_000), _row(cutoff, 50.0, 500_000)],  # a bar after the scan may not count
        "SEEN": [_row(_at(9, 0), 3.0, 500_000)],
        "THIN": [_row(_at(9, 0), 90.0, 1)],
    }

    gainers = replay.rank_premarket_gainers(closes, bars, cutoff=cutoff, size=2)

    assert [gainer.symbol for gainer in gainers] == ["SEEN", "LATE"]
    assert gainers[1].premarket_price == Decimal("1.1")


def test_an_empty_minute_is_a_flat_bar_with_no_volume() -> None:
    rows = [_row(_at(9, 30), 10.0), _row(_at(9, 32), 11.0)]

    tape = replay.build_minute_tape("TEST", INSTRUMENT, rows, session=SESSION, previous_close=Decimal("9"))

    regular = [bar for bar in tape if bar.session == "regular"]
    assert len(regular) == 390
    empty = regular[1]
    assert empty.volume == 0 and empty.open == empty.high == empty.low == empty.close == Decimal("10.0")
    assert regular[2].close == Decimal("11.0")


def test_bars_end_at_the_simulated_clock() -> None:
    now = _at(10, 0, 5)
    bars = _market(now).bars(INSTRUMENT, "1m", 500).bars

    assert max(bar.end_time for bar in bars) == _at(10, 0)


def test_recovered_bars_are_cut_at_the_earlier_of_as_of_and_the_clock() -> None:
    market = _market(_at(10, 0, 5))

    future = market.recovered_bars(INSTRUMENT, "1m", 500, session_date=SESSION, as_of=_at(15, 0)).bars
    earlier = market.recovered_bars(INSTRUMENT, "1m", 500, session_date=SESSION, as_of=_at(9, 45)).bars

    assert max(bar.end_time for bar in future) == _at(10, 0)
    assert max(bar.end_time for bar in earlier) == _at(9, 45)


def test_a_fill_uses_the_first_quote_after_the_decision() -> None:
    archive = _Archive()
    market = _market(_at(10, 0, 5), archive)
    decided = _at(10, 0, 22)

    selection = market.first_causal_after(INSTRUMENT, decision_completed_at=decided, actionable_at=_at(10, 0, 5))

    assert archive.asked[-1]["after"] == decided + replay.ORDER_LATENCY
    assert selection.observation.source_time >= decided + replay.ORDER_LATENCY


def test_a_fill_looks_only_after_the_time_the_monitor_passes() -> None:
    archive = _Archive()
    market = _market(_at(10, 30, 5), archive)

    market.first_causal_after(INSTRUMENT, decision_completed_at=_at(10, 29, 5), actionable_at=_at(10, 29, 5))

    assert archive.asked[-1]["after"] == _at(10, 29, 5) + replay.ORDER_LATENCY


def test_concurrent_mode_runs_every_monitor_together() -> None:
    import asyncio

    calls: list[str] = []

    class Monitor:
        last_error = None

        def __init__(self, name):
            self.name = name

        async def run_once(self):
            calls.append(f"start-{self.name}")
            await asyncio.sleep(0)
            calls.append(f"end-{self.name}")

    clock = replay.SimClock(_at(9, 31))
    asyncio.run(replay.run_replay({"A": Monitor("A"), "B": Monitor("B")}, clock, [_at(9, 31)], progress=lambda _: None, concurrent=True))

    assert calls[:2] == ["start-A", "start-B"]


def test_a_fill_quote_is_taken_at_the_current_second() -> None:
    archive = _Archive()
    now = _at(10, 0, 7)

    _market(now, archive).execution_observation(INSTRUMENT)

    assert archive.asked[-1]["before"] == now


def test_a_decision_sees_only_quotes_already_known() -> None:
    archive = _Archive()
    now = _at(10, 0, 7)

    envelope = _market(now, archive).latest(INSTRUMENT, as_of=_at(15, 0))

    assert archive.asked[-1]["before"] <= now
    assert envelope.observation.source_time <= now


def test_a_wide_quote_is_not_fillable() -> None:
    market = _market(_at(10, 0, 5))

    observation = market._observation(INSTRUMENT, {"t": replay.utc_iso(_at(10, 0)), "bp": 9.0, "ap": 11.0})

    assert observation.execution_eligible is False and observation.paper_fill_eligible is False


def test_a_headline_is_visible_only_from_its_publication() -> None:
    published = _at(9, 40)
    rows = [{"id": 1, "created_at": replay.utc_iso(published), "headline": "Deal", "summary": "", "symbols": ["TEST"]}]
    repository = replay.ReplayResearchRepository(replay.news_evidence(rows, {"TEST": INSTRUMENT}))

    assert repository.list_evidence_as_of(INSTRUMENT, published - timedelta(seconds=1)) == []
    assert [item.title for item in repository.list_evidence_as_of(INSTRUMENT, published)] == ["Deal"]


def _event(key: str, observed_at: datetime, event_type: str = "ai_v3_fill") -> SimpleNamespace:
    return SimpleNamespace(idempotency_key=key, strategy_id="s", observed_at=observed_at, event_type=event_type)


def test_the_repository_is_idempotent_and_serves_a_time_window() -> None:
    repository = replay.ReplayRepository(SimpleNamespace(strategy_id="s"), "universe")
    later, earlier = _event("b", _at(10, 5)), _event("a", _at(10, 0))

    assert repository.append_event(later) is True
    assert repository.append_event(later) is False
    repository.append_event(earlier)

    window = repository.events_by_types_between("s", event_types=("ai_v3_fill",), start_time=_at(9, 30), end_time=_at(11, 0))
    assert window == [earlier, later]
    assert repository.recent_events("s", 1) == [later]


def test_the_simulated_clock_advances_with_real_model_time(monkeypatch) -> None:
    ticks = iter([100.0, 117.0])
    monkeypatch.setattr(replay.time_module, "monotonic", lambda: next(ticks))
    clock = replay.SimClock(_at(10, 0, 5))

    assert clock.now() == _at(10, 0, 22)


def test_steps_reach_the_morning_freeze_every_minute_and_the_close() -> None:
    steps = replay.replay_steps(SESSION)

    assert steps == sorted(steps)
    assert steps[0] == _at(9, 16, 5)
    assert _at(12, 0, 5) in steps
    assert steps[-1] == _at(16, 40, 5)
    assert replay.replay_steps(SESSION, until=time(9, 31, 30))[-1] == _at(9, 31, 5)


def test_the_catalyst_analyzer_runs_through_its_policy() -> None:
    """The bound method once passed the analyzer twice, so every assessment raised TypeError."""
    from app.apps.trading.strategy_ai_shadow_v2 import CatalystIntelligenceAnalyzer

    snapshot = CatalystIntelligenceAnalyzer(provider_factory=lambda: None).assess(
        instrument_id=INSTRUMENT, as_of=_at(9, 20), report=None, evidence=[],
    )

    assert snapshot.instrument_id == INSTRUMENT and snapshot.intraday_persistence_class == "uncertain"


def test_the_quote_helper_needs_one_direction(tmp_path) -> None:
    archive = replay.AlpacaArchive(tmp_path, session=SimpleNamespace())

    with pytest.raises(ValueError):
        archive.quote("TEST")
