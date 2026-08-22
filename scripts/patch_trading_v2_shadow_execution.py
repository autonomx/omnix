from __future__ import annotations

"""One-shot guarded integration of V2 SHADOW execution evidence.

The transformation is intentionally exact: if the monitor import or the boundary
between deterministic proposal evaluation and AUTO PAPER order work has moved,
this script refuses to write anything.
"""

from pathlib import Path


MONITOR = Path("src/app/trading/strategy_monitor.py")
TEST = Path("src/tests/trading/test_trading_strategy_shadow_execution.py")


IMPORT_OLD = """from .strategy_research_policy import apply_research_policy_to_quality, resolve_strategy_research_policy\nfrom .strategy_risk import size_strategy_entry\nfrom .strategy_v2_management import (\n"""
IMPORT_NEW = """from .strategy_research_policy import apply_research_policy_to_quality, resolve_strategy_research_policy\nfrom .strategy_risk import size_strategy_entry\nfrom .strategy_shadow_execution import observe_shadow_execution\nfrom .strategy_v2_management import (\n"""

BOUNDARY_OLD = """        proposals = await self._evaluate_candidates(\n            config,\n            strategy_repository,\n            market_service,\n            universe,\n        )\n        if config.mode != \"auto_paper\" or not proposals:\n            trade_log(\n                \"auto_trading\",\n                \"strategy_cycle_no_entry_work\",\n                run_id=self.current_run_id,\n                strategy_id=config.strategy_id,\n                mode=config.mode,\n                proposal_count=len(proposals),\n            )\n            return\n\n        snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)\n"""

BOUNDARY_NEW = """        proposals = await self._evaluate_candidates(\n            config,\n            strategy_repository,\n            market_service,\n            universe,\n        )\n        if config.mode == \"shadow\" and proposals:\n            for proposal in proposals:\n                candidate = proposal.candidate\n                result = proposal.result\n                assert result.signal is not None\n                try:\n                    evidence = await asyncio.to_thread(\n                        observe_shadow_execution,\n                        market_service,\n                        instrument_id=candidate.instrument_id,\n                        binding_id=candidate.binding_id,\n                    )\n                except Exception as exc:\n                    payload = {\n                        \"strategy_version\": config.config.strategy_version,\n                        \"mode\": \"shadow\",\n                        \"universe_id\": universe.universe_id,\n                        \"signal\": result.signal.model_dump(mode=\"json\"),\n                        \"features\": result.features.model_dump(mode=\"json\"),\n                        \"error_type\": type(exc).__name__,\n                        \"detail\": str(exc),\n                        \"execution_authority\": False,\n                    }\n                    await self._event(\n                        strategy_repository,\n                        config,\n                        instrument_id=candidate.instrument_id,\n                        event_type=\"shadow_execution\",\n                        state=result.state,\n                        reason_code=\"SHADOW_EXECUTION_UNAVAILABLE\",\n                        observed_at=proposal.observed_at,\n                        payload=payload,\n                    )\n                    trade_log(\n                        \"auto_trading\",\n                        \"shadow_execution_unavailable\",\n                        run_id=self.current_run_id,\n                        strategy_id=config.strategy_id,\n                        instrument_id=candidate.instrument_id,\n                        **payload,\n                    )\n                    continue\n\n                payload = {\n                    \"strategy_version\": config.config.strategy_version,\n                    \"mode\": \"shadow\",\n                    \"universe_id\": universe.universe_id,\n                    \"signal\": result.signal.model_dump(mode=\"json\"),\n                    \"features\": result.features.model_dump(mode=\"json\"),\n                    \"execution\": evidence.execution,\n                    \"execution_authority\": False,\n                }\n                await self._event(\n                    strategy_repository,\n                    config,\n                    instrument_id=candidate.instrument_id,\n                    event_type=\"shadow_execution\",\n                    state=result.state,\n                    reason_code=evidence.reason_code,\n                    observed_at=proposal.observed_at,\n                    payload=payload,\n                )\n                trade_log(\n                    \"auto_trading\",\n                    \"shadow_execution_observation\",\n                    run_id=self.current_run_id,\n                    strategy_id=config.strategy_id,\n                    instrument_id=candidate.instrument_id,\n                    reason_code=evidence.reason_code,\n                    **payload,\n                )\n\n            trade_log(\n                \"auto_trading\",\n                \"strategy_cycle_no_entry_work\",\n                run_id=self.current_run_id,\n                strategy_id=config.strategy_id,\n                mode=config.mode,\n                proposal_count=len(proposals),\n                shadow_execution_observed=True,\n            )\n            return\n\n        if config.mode != \"auto_paper\" or not proposals:\n            trade_log(\n                \"auto_trading\",\n                \"strategy_cycle_no_entry_work\",\n                run_id=self.current_run_id,\n                strategy_id=config.strategy_id,\n                mode=config.mode,\n                proposal_count=len(proposals),\n            )\n            return\n\n        snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)\n"""

TEST_APPEND = '''\n\ndef test_strategy_monitor_shadow_observation_precedes_auto_paper_order_boundary() -> None:\n    source = Path("src/app/trading/strategy_monitor.py").read_text(encoding="utf-8")\n    shadow_start = source.index('if config.mode == "shadow" and proposals:')\n    auto_paper_start = source.index(\n        "snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)",\n        shadow_start,\n    )\n    shadow_block = source[shadow_start:auto_paper_start]\n\n    assert "observe_shadow_execution" in shadow_block\n    assert 'event_type="shadow_execution"' in shadow_block\n    assert '"execution_authority": False' in shadow_block\n    assert "place_order" not in shadow_block\n    assert "save_protection" not in shadow_block\n'''


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    monitor = MONITOR.read_text(encoding="utf-8")
    monitor = replace_exact(monitor, IMPORT_OLD, IMPORT_NEW, "monitor import")
    monitor = replace_exact(monitor, BOUNDARY_OLD, BOUNDARY_NEW, "AUTO PAPER boundary")

    tests = TEST.read_text(encoding="utf-8")
    marker = "def test_strategy_monitor_shadow_observation_precedes_auto_paper_order_boundary()"
    if marker not in tests:
        tests += TEST_APPEND

    MONITOR.write_text(monitor, encoding="utf-8")
    TEST.write_text(tests, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
