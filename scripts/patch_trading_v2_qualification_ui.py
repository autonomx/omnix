from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one guarded match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/app/trading/strategy_shadow_universe.py",
    '''def resolve_v2_shadow_archive_for_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    session_date: date,
):
    """Return one raw strategy-owned V2 SHADOW archive by session date.

    This is a read-only evidence lookup. It never attaches a universe to the
    strategy and is intentionally unavailable to AUTO PAPER, non-V2 strategies,
    or SHADOW configs that already carry an explicit active universe.
    """

    if (
        config.mode != "shadow"
        or config.config.strategy_version != "2.0.0"
        or config.active_universe_id is not None
    ):
        return None

    marker = datetime.combine(session_date, config.config.universe_scan_time_et, tzinfo=_ET)
    universe_id = _archive_universe_id(config, marker)
    try:
        snapshot = repository.get_universe(universe_id)
    except ValueError as exc:
        if str(exc) == "gapper_universe_not_found":
            return None
        raise
    if snapshot.session_date != session_date:
        return None
    return snapshot
''',
    '''def resolve_v2_evidence_archive_for_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    session_date: date,
):
    """Return the immutable strategy-owned V2 raw archive for qualification evidence.

    This resolver is deliberately read-only and independent of ``active_universe_id``.
    It may be used while V2 is in SHADOW or AUTO PAPER so post-session evidence keeps
    accumulating after promotion. It never attaches the archive to the strategy and
    therefore cannot grant order authority.
    """

    if config.mode not in {"shadow", "auto_paper"} or config.config.strategy_version != "2.0.0":
        return None

    marker = datetime.combine(session_date, config.config.universe_scan_time_et, tzinfo=_ET)
    universe_id = _archive_universe_id(config, marker)
    try:
        snapshot = repository.get_universe(universe_id)
    except ValueError as exc:
        if str(exc) == "gapper_universe_not_found":
            return None
        raise
    if snapshot.session_date != session_date:
        return None
    return snapshot


def resolve_v2_shadow_archive_for_session(
    config: TradingStrategyConfigDocument,
    repository: TradingStrategyRepository,
    *,
    session_date: date,
):
    """Return one raw strategy-owned archive only for the V2 SHADOW execution fallback.

    Unlike the qualification evidence resolver, this path remains unavailable to
    AUTO PAPER and to SHADOW configs with an explicitly selected universe.
    """

    if config.mode != "shadow" or config.active_universe_id is not None:
        return None
    return resolve_v2_evidence_archive_for_session(
        config,
        repository,
        session_date=session_date,
    )
''',
)

replace_once(
    "src/app/trading/strategy_shadow_universe.py",
    '__all__ = ["resolve_v2_shadow_archive", "resolve_v2_shadow_archive_for_session"]',
    '__all__ = [\n    "resolve_v2_evidence_archive_for_session",\n    "resolve_v2_shadow_archive",\n    "resolve_v2_shadow_archive_for_session",\n]',
)

replace_once(
    "src/app/trading/strategy_v2_qualification_monitor.py",
    'from .strategy_shadow_universe import resolve_v2_shadow_archive_for_session',
    'from .strategy_shadow_universe import resolve_v2_evidence_archive_for_session',
)
replace_once(
    "src/app/trading/strategy_v2_qualification_monitor.py",
    '        and config.mode == "shadow"\n',
    '        and config.mode in {"shadow", "auto_paper"}\n',
)
replace_once(
    "src/app/trading/strategy_v2_qualification_monitor.py",
    '    """Replay one already-captured prospective SHADOW session without order authority."""',
    '    """Replay one captured prospective V2 session as evidence without order authority."""',
)
replace_once(
    "src/app/trading/strategy_v2_qualification_monitor.py",
    '    universe = resolve_v2_shadow_archive_for_session(config, repository, session_date=session_date)',
    '    universe = resolve_v2_evidence_archive_for_session(config, repository, session_date=session_date)',
)
replace_once(
    "src/app/trading/strategy_v2_qualification_monitor.py",
    'class TradingStrategyV2QualificationMonitor:\n    """Evidence-only prospective V2 replay monitor; never creates orders."""',
    'class TradingStrategyV2QualificationMonitor:\n    """Evidence-only prospective V2 replay monitor across SHADOW/AUTO PAPER; never creates orders."""',
)

replace_once(
    "src/tests/trading/test_trading_strategy_shadow_universe.py",
    'from app.trading.strategy_shadow_universe import resolve_v2_shadow_archive',
    'from app.trading.strategy_shadow_universe import (\n    resolve_v2_evidence_archive_for_session,\n    resolve_v2_shadow_archive,\n)',
)
replace_once(
    "src/tests/trading/test_trading_strategy_shadow_universe.py",
    '''def test_shadow_archive_fallback_never_applies_to_auto_paper_or_explicit_universe() -> None:
    repository = FakeRepository()
    assert resolve_v2_shadow_archive(_config(mode="auto_paper"), repository, now=NOW) is None
    assert resolve_v2_shadow_archive(_config(active="selected-universe"), repository, now=NOW) is None
    assert repository.reads == []
''',
    '''def test_shadow_archive_fallback_never_applies_to_auto_paper_or_explicit_universe() -> None:
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
''',
)

replace_once(
    "src/tests/trading/test_trading_strategy_v2_qualification_monitor.py",
    'def _strategy():\n',
    'def _strategy(*, mode: str = "shadow", active_universe_id: str | None = None):\n',
)
replace_once(
    "src/tests/trading/test_trading_strategy_v2_qualification_monitor.py",
    '        mode="shadow",\n        active_universe_id=None,\n',
    '        mode=mode,\n        active_universe_id=active_universe_id,\n',
)
replace_once(
    "src/tests/trading/test_trading_strategy_v2_qualification_monitor.py",
    '''def test_post_session_replay_refuses_noncanonical_v2_profile() -> None:
''',
    '''def test_post_session_replay_continues_after_auto_paper_promotion() -> None:
    strategy = _strategy(mode="auto_paper", active_universe_id="selected-universe")
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
    assert repository.events[0].event_type == "v2_shadow_replay_session"
    assert repository.events[0].payload["execution_authority"] is False
    assert strategy.active_universe_id == "selected-universe"


def test_post_session_replay_refuses_noncanonical_v2_profile() -> None:
''',
)
