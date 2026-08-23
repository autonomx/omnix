from __future__ import annotations

"""One-shot guarded integration of raw auto-archive fallback for V2 SHADOW."""

from pathlib import Path


MONITOR = Path("src/app/trading/strategy_monitor.py")
TEST = Path("src/tests/trading/test_trading_strategy_shadow_universe.py")

IMPORT_OLD = """from .strategy_risk import size_strategy_entry\nfrom .strategy_shadow_execution import observe_shadow_execution\nfrom .strategy_v2_management import (\n"""
IMPORT_NEW = """from .strategy_risk import size_strategy_entry\nfrom .strategy_shadow_execution import observe_shadow_execution\nfrom .strategy_shadow_universe import resolve_v2_shadow_archive\nfrom .strategy_v2_management import (\n"""

BOUNDARY_OLD = """        if config.mode == \"off\" or not config.enabled or not config.active_universe_id:\n            trade_log(\n                \"auto_trading\",\n                \"strategy_cycle_skipped\",\n                run_id=self.current_run_id,\n                strategy_id=config.strategy_id,\n                reason=(\n                    \"mode_off\"\n                    if config.mode == \"off\"\n                    else \"disabled\"\n                    if not config.enabled\n                    else \"no_active_universe\"\n                ),\n            )\n            return\n\n        now_utc = datetime.now(timezone.utc)\n        now_et = now_utc.astimezone(_ET)\n        today_et = now_et.date()\n        day_start_et = datetime(today_et.year, today_et.month, today_et.day, tzinfo=_ET)\n        day_end_et = day_start_et + timedelta(days=1)\n\n        universe = await asyncio.to_thread(\n            strategy_repository.get_universe,\n            config.active_universe_id,\n        )\n        trade_log(\n            \"auto_trading\",\n            \"universe_loaded\",\n            run_id=self.current_run_id,\n            strategy_id=config.strategy_id,\n            universe_id=universe.universe_id,\n            session_date=universe.session_date,\n            evaluation_time=universe.evaluation_time,\n            discovery_source=universe.discovery_source,\n            source_fingerprint=universe.source_fingerprint,\n            candidate_count=len(universe.candidates),\n        )\n"""

BOUNDARY_NEW = """        if config.mode == \"off\" or not config.enabled:\n            trade_log(\n                \"auto_trading\",\n                \"strategy_cycle_skipped\",\n                run_id=self.current_run_id,\n                strategy_id=config.strategy_id,\n                reason=\"mode_off\" if config.mode == \"off\" else \"disabled\",\n            )\n            return\n\n        now_utc = datetime.now(timezone.utc)\n        now_et = now_utc.astimezone(_ET)\n        today_et = now_et.date()\n        day_start_et = datetime(today_et.year, today_et.month, today_et.day, tzinfo=_ET)\n        day_end_et = day_start_et + timedelta(days=1)\n\n        universe_source = \"active_universe\"\n        if config.active_universe_id is not None:\n            universe = await asyncio.to_thread(\n                strategy_repository.get_universe,\n                config.active_universe_id,\n            )\n        else:\n            universe = await asyncio.to_thread(\n                resolve_v2_shadow_archive,\n                config,\n                strategy_repository,\n                now=now_utc,\n            )\n            universe_source = \"auto_archive_shadow\"\n            if universe is None:\n                trade_log(\n                    \"auto_trading\",\n                    \"strategy_cycle_skipped\",\n                    run_id=self.current_run_id,\n                    strategy_id=config.strategy_id,\n                    reason=(\n                        \"v2_shadow_archive_not_ready\"\n                        if config.mode == \"shadow\" and config.config.strategy_version == \"2.0.0\"\n                        else \"no_active_universe\"\n                    ),\n                )\n                return\n\n        trade_log(\n            \"auto_trading\",\n            \"universe_loaded\",\n            run_id=self.current_run_id,\n            strategy_id=config.strategy_id,\n            universe_id=universe.universe_id,\n            runtime_universe_source=universe_source,\n            session_date=universe.session_date,\n            evaluation_time=universe.evaluation_time,\n            discovery_source=universe.discovery_source,\n            source_fingerprint=universe.source_fingerprint,\n            candidate_count=len(universe.candidates),\n        )\n"""

PAYLOAD_OLD = """                        \"mode\": \"shadow\",\n                        \"universe_id\": universe.universe_id,\n                        \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
PAYLOAD_NEW = """                        \"mode\": \"shadow\",\n                        \"universe_id\": universe.universe_id,\n                        \"universe_source\": universe_source,\n                        \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
PAYLOAD2_OLD = """                    \"mode\": \"shadow\",\n                    \"universe_id\": universe.universe_id,\n                    \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
PAYLOAD2_NEW = """                    \"mode\": \"shadow\",\n                    \"universe_id\": universe.universe_id,\n                    \"universe_source\": universe_source,\n                    \"signal\": result.signal.model_dump(mode=\"json\"),\n"""

TEST_APPEND = '''\n\ndef test_strategy_monitor_uses_raw_archive_only_as_v2_shadow_fallback() -> None:\n    source = Path("src/app/trading/strategy_monitor.py").read_text(encoding="utf-8")\n    fallback = source.index("resolve_v2_shadow_archive")\n    evaluation = source.index("proposals = await self._evaluate_candidates", fallback)\n    block = source[fallback:evaluation]\n\n    assert 'universe_source = "auto_archive_shadow"' in block\n    assert '"v2_shadow_archive_not_ready"' in block\n    assert "config.active_universe_id is not None" in block\n    assert "place_order" not in block\n    assert "save_protection" not in block\n'''


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    monitor = MONITOR.read_text(encoding="utf-8")
    monitor = replace_exact(monitor, IMPORT_OLD, IMPORT_NEW, "monitor import")
    monitor = replace_exact(monitor, BOUNDARY_OLD, BOUNDARY_NEW, "universe boundary")
    monitor = replace_exact(monitor, PAYLOAD_OLD, PAYLOAD_NEW, "shadow unavailable payload")
    monitor = replace_exact(monitor, PAYLOAD2_OLD, PAYLOAD2_NEW, "shadow observed payload")
    MONITOR.write_text(monitor, encoding="utf-8")

    tests = TEST.read_text(encoding="utf-8")
    marker = "def test_strategy_monitor_uses_raw_archive_only_as_v2_shadow_fallback()"
    if marker not in tests:
        tests += TEST_APPEND
    TEST.write_text(tests, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
