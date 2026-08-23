from __future__ import annotations

from datetime import datetime, timezone

from app.trading.gapper_dataset import freeze_gapper_universe
from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from app.trading.strategy_universe_archiver import _archive_universe_id
from app.trading.strategy_v2_qualification import frozen_v2_config
from app.trading.strategy_v2_qualification_monitor import replay_v2_shadow_session


SESSION_NOW = datetime(2026, 8, 24, 20, 30, tzinfo=timezone.utc)  # after 16:00 ET + grace


class FakeRepository:
    def __init__(self, universe) -> None:
        self.universe = universe
        self.events: list[StrategyEvent] = []
        self.writes = 0

    def get_universe(self, universe_id: str):
        if universe_id != self.universe.universe_id:
            raise ValueError("gapper_universe_not_found")
        return self.universe

    def recent_events(self, strategy_id: str, limit: int = 200):
        assert strategy_id == "v2-prospective"
        return list(reversed(self.events[-limit:]))

    def append_event(self, event: StrategyEvent) -> bool:
        if any(existing.idempotency_key == event.idempotency_key for existing in self.events):
            return False
        self.events.append(event)
        self.writes += 1
        return True


def _strategy():
    config = frozen_v2_config()
    return TradingStrategyConfigDocument(
        strategy_id="v2-prospective",
        account_id="paper-1",
        strategy_kind="gap_pullback_v1",
        strategy_version="2.0.0",
        mode="shadow",
        active_universe_id=None,
        config=config,
        risk=StrategyRiskProfile(),
        enabled=True,
    )


def test_post_session_replay_persists_completed_zero_trade_session_once() -> None:
    strategy = _strategy()
    universe_id = _archive_universe_id(strategy, SESSION_NOW.astimezone())
    universe = freeze_gapper_universe(
        universe_id=universe_id,
        session_date=SESSION_NOW.astimezone().date(),
        evaluation_time=datetime(2026, 8, 24, 13, 20, tzinfo=timezone.utc),
        discovery_source="provider",
        candidates=[],
        allow_empty=True,
    )
    repository = FakeRepository(universe)

    result = replay_v2_shadow_session(
        strategy,
        repository,
        universe.session_date,
        observed_at=SESSION_NOW,
        bar_loader=lambda candidates, session_date: {},
    )

    assert result is not None
    assert result.summary.trade_count == 0
    assert repository.writes == 1
    session_event = repository.events[0]
    assert session_event.event_type == "v2_shadow_replay_session"
    assert session_event.payload["status"] == "completed"
    assert session_event.payload["universe_source"] == "auto_archive_shadow"
    assert session_event.payload["assumed_spread_bps"] == "150"
    assert session_event.payload["execution_authority"] is False

    second = replay_v2_shadow_session(
        strategy,
        repository,
        universe.session_date,
        observed_at=SESSION_NOW,
        bar_loader=lambda candidates, session_date: {},
    )
    assert second is None
    assert repository.writes == 1


def test_post_session_replay_refuses_noncanonical_v2_profile() -> None:
    strategy = _strategy()
    strategy = strategy.model_copy(
        update={
            "config": strategy.config.model_copy(update={"v2_maximum_l2_to_signal_minutes": 9}),
        }
    )
    universe_id = _archive_universe_id(strategy, SESSION_NOW.astimezone())
    universe = freeze_gapper_universe(
        universe_id=universe_id,
        session_date=SESSION_NOW.astimezone().date(),
        evaluation_time=datetime(2026, 8, 24, 13, 20, tzinfo=timezone.utc),
        discovery_source="provider",
        candidates=[],
        allow_empty=True,
    )
    repository = FakeRepository(universe)

    assert replay_v2_shadow_session(
        strategy,
        repository,
        universe.session_date,
        observed_at=SESSION_NOW,
        bar_loader=lambda candidates, session_date: {},
    ) is None
    assert repository.writes == 0
