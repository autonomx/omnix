from __future__ import annotations

from datetime import datetime, timezone

from app.trading.gapper_dataset import freeze_gapper_universe
from app.trading.strategies.models import GapPullbackConfig, StrategyRiskProfile
from app.trading.strategy_repository import TradingStrategyConfigDocument
from app.trading.strategy_shadow_universe import (
    resolve_v2_evidence_archive_for_session,
    resolve_v2_shadow_archive,
)
from app.trading.strategy_universe_archiver import _archive_universe_id


NOW = datetime(2026, 8, 24, 13, 25, tzinfo=timezone.utc)  # 09:25 ET


class FakeRepository:
    def __init__(self, universes=None) -> None:
        self.universes = universes or {}
        self.reads: list[str] = []
        self.writes = 0

    def get_universe(self, universe_id: str):
        self.reads.append(universe_id)
        if universe_id not in self.universes:
            raise ValueError("gapper_universe_not_found")
        return self.universes[universe_id]


def _config(*, mode: str = "shadow", version: str = "2.0.0", active: str | None = None):
    config = GapPullbackConfig(
        strategy_version=version,
        structure_interval="1m" if version == "2.0.0" else "5m",
        execution_interval="1m",
    )
    return TradingStrategyConfigDocument(
        strategy_id="prospective-v2",
        account_id="paper-1",
        strategy_kind="gap_pullback_v1",
        strategy_version=version,
        mode=mode,
        active_universe_id=active,
        enabled=True,
        config=config,
        risk=StrategyRiskProfile(),
    )


def test_v2_shadow_resolves_today_raw_archive_without_mutating_config() -> None:
    config = _config()
    universe_id = _archive_universe_id(config, NOW.astimezone())
    snapshot = freeze_gapper_universe(
        universe_id=universe_id,
        session_date=NOW.astimezone().date(),
        evaluation_time=NOW,
        discovery_source="provider",
        candidates=[],
        allow_empty=True,
    )
    repository = FakeRepository({universe_id: snapshot})

    resolved = resolve_v2_shadow_archive(config, repository, now=NOW)

    assert resolved == snapshot
    assert repository.reads == [universe_id]
    assert repository.writes == 0
    assert config.active_universe_id is None


def test_v2_shadow_waits_when_archive_is_not_ready() -> None:
    repository = FakeRepository()
    assert resolve_v2_shadow_archive(_config(), repository, now=NOW) is None
    assert len(repository.reads) == 1


def test_shadow_archive_fallback_never_applies_to_auto_paper_or_explicit_universe() -> None:
    repository = FakeRepository()
    assert resolve_v2_shadow_archive(_config(mode="auto_paper"), repository, now=NOW) is None
    assert resolve_v2_shadow_archive(_config(active="selected-universe"), repository, now=NOW) is None
    assert repository.reads == []


def test_v2_evidence_archive_remains_read_only_after_auto_paper_promotion() -> None:
    config = _config(mode="auto_paper", active="selected-universe")
    universe_id = _archive_universe_id(config, NOW.astimezone())
    snapshot = freeze_gapper_universe(
        universe_id=universe_id,
        session_date=NOW.astimezone().date(),
        evaluation_time=NOW,
        discovery_source="provider",
        candidates=[],
        allow_empty=True,
    )
    repository = FakeRepository({universe_id: snapshot})

    resolved = resolve_v2_evidence_archive_for_session(
        config,
        repository,
        session_date=NOW.astimezone().date(),
    )

    assert resolved == snapshot
    assert repository.reads == [universe_id]
    assert repository.writes == 0
    assert config.active_universe_id == "selected-universe"
