from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.strategy_managed_finviz_shadow import (
    INTERDAY_TRADING_STRATEGY_ID,
    managed_finviz_shadow_document,
    managed_stoch_rsi_guarded_document,
)
from app.trading.strategy_shadow_universe import resolve_stoch_rsi_5m_runtime_archive
from app.trading.strategy_universe_archiver import _archive_universe_id


_ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)


class _Repository:
    def __init__(self, parent, universe) -> None:
        self.parent = parent
        self.universe = universe

    def get_config(self, strategy_id: str):
        if strategy_id != INTERDAY_TRADING_STRATEGY_ID:
            raise ValueError("strategy_config_not_found")
        return self.parent

    def get_universe(self, universe_id: str):
        if universe_id != self.universe.universe_id:
            raise ValueError("gapper_universe_not_found")
        return self.universe


def test_guarded_child_reuses_parent_frozen_benchmark_archive() -> None:
    parent = managed_finviz_shadow_document("paper-test")
    child = managed_stoch_rsi_guarded_document("paper-test")
    session_date = NOW.astimezone(_ET).date()
    marker = datetime.combine(
        session_date,
        parent.config.universe_scan_time_et,
        tzinfo=_ET,
    )
    parent_universe_id = _archive_universe_id(parent, marker)
    candidate = GapperCandidate(
        instrument_id="equity:NASDAQ:TEST",
        observed_at=marker.astimezone(timezone.utc),
        previous_close=Decimal("10"),
        premarket_price=Decimal("12.50"),
        gap_pct=Decimal("25"),
        discovery_rank=1,
    )
    frozen = freeze_gapper_universe(
        universe_id=parent_universe_id,
        session_date=session_date,
        evaluation_time=marker.astimezone(timezone.utc),
        discovery_source="finviz",
        source_candidate_symbols=("TEST",),
        candidates=(candidate,),
    )

    resolved = resolve_stoch_rsi_5m_runtime_archive(
        child,
        _Repository(parent, frozen),
        now=NOW,
    )

    assert resolved is not None
    assert resolved.universe_id == parent_universe_id
    assert resolved.candidates == frozen.candidates
    assert child.parent_strategy_id == INTERDAY_TRADING_STRATEGY_ID
    assert child.config.policy_profile == "guarded_v1"
    assert child.config.universe_scan_time_et == parent.config.universe_scan_time_et
    assert child.config.universe_discovery_source == "finviz"
    assert child.config.universe_discovery_count == 5
    assert child.config.auto_archive_daily_universe is False
