from __future__ import annotations

from datetime import datetime, time, timezone

from app.trading.gapper_dataset import freeze_gapper_universe
from app.trading.providers.errors import ProviderDataUnavailableError
from app.trading.strategies.models import GapPullbackConfig
from app.trading.strategy_repository import TradingStrategyConfigDocument
from app.trading import strategy_universe_archiver as archiver


class FakeRepository:
    def __init__(self):
        self.values = {}

    def get_universe(self, universe_id):
        if universe_id not in self.values:
            raise ValueError("gapper_universe_not_found")
        return self.values[universe_id]

    def save_universe(self, snapshot):
        self.values[snapshot.universe_id] = snapshot
        return snapshot


def strategy() -> TradingStrategyConfigDocument:
    return TradingStrategyConfigDocument(
        strategy_id="archive-test",
        account_id="paper-1",
        strategy_version="1.1.0",
        mode="shadow",
        enabled=True,
        config=GapPullbackConfig(
            strategy_version="1.1.0",
            universe_scan_time_et=time(9, 20),
            auto_archive_daily_universe=True,
            universe_archive_grace_minutes=10,
        ),
    )


def test_archiver_saves_one_evidence_only_snapshot_and_is_idempotent(monkeypatch) -> None:
    repository = FakeRepository()
    calls = []

    def discover(**kwargs):
        calls.append(kwargs)
        observed = kwargs["evaluation_time"]
        return freeze_gapper_universe(
            universe_id=kwargs["universe_id"],
            session_date=observed.date(),
            evaluation_time=observed,
            discovery_source="provider",
            candidates=[],
            allow_empty=True,
        )

    monkeypatch.setattr(archiver, "discover_yahoo_gappers", discover)
    now = datetime(2026, 8, 19, 13, 22, tzinfo=timezone.utc)  # 09:22 ET

    first = archiver.archive_daily_universe_if_due(strategy(), repository, now=now)
    second = archiver.archive_daily_universe_if_due(strategy(), repository, now=now)

    assert first is not None
    assert second is first
    assert len(calls) == 1
    assert len(first.candidates) == 0
    assert first.universe_id.startswith("auto-archive-2026-08-19-0920-")


def test_archiver_preserves_completed_zero_candidate_scan(monkeypatch) -> None:
    repository = FakeRepository()

    def no_candidates(**kwargs):
        raise ProviderDataUnavailableError("Yahoo top-gainers produced no qualifying listed equities")

    monkeypatch.setattr(archiver, "discover_yahoo_gappers", no_candidates)
    now = datetime(2026, 8, 19, 13, 25, tzinfo=timezone.utc)  # 09:25 ET

    snapshot = archiver.archive_daily_universe_if_due(strategy(), repository, now=now)

    assert snapshot is not None
    assert snapshot.candidates == ()
    assert repository.get_universe(snapshot.universe_id) is snapshot


def test_archiver_does_not_backfill_hours_after_configured_scan(monkeypatch) -> None:
    repository = FakeRepository()
    called = False

    def discover(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not run")

    monkeypatch.setattr(archiver, "discover_yahoo_gappers", discover)
    now = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)  # noon ET

    assert archiver.archive_daily_universe_if_due(strategy(), repository, now=now) is None
    assert called is False
