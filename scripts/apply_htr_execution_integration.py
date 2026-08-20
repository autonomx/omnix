from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"HTR patch anchor not found in {path}: {old[:120]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"HTR patch anchor is ambiguous in {path}: {text.count(old)} matches")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_monitor() -> None:
    path = "src/app/trading/strategy_monitor.py"
    replace_once(
        path,
        "from .strategy_risk import size_strategy_entry\n",
        "from .strategy_research_policy import resolve_strategy_research_policy\nfrom .strategy_risk import size_strategy_entry\n",
    )
    replace_once(
        path,
        '''            if result.state == "entry_ready" and result.signal is not None:\n                self.signal_count += 1\n                proposals.append(\n''',
        '''            if result.state == "entry_ready" and result.signal is not None:\n                self.signal_count += 1\n                if config.config.strategy_version == "1.2.0":\n                    try:\n                        research_decision = await asyncio.to_thread(\n                            resolve_strategy_research_policy,\n                            strategy_version=config.config.strategy_version,\n                            instrument_id=candidate.instrument_id,\n                            decision_at=observed_at,\n                        )\n                    except Exception as exc:\n                        research_decision = None\n                        reason_code = "RESEARCH_POLICY_RESOLUTION_ERROR"\n                        detail = f"{type(exc).__name__}: {exc}"\n                    else:\n                        reason_code = research_decision.reason_code\n                        detail = None\n                    allowed = research_decision is not None and research_decision.allowed\n                    payload = {\n                        "strategy_version": config.config.strategy_version,\n                        "policy_version": (\n                            research_decision.policy_version if research_decision is not None else "trading-research-1"\n                        ),\n                        "authoritative": True,\n                        "allowed": allowed,\n                        "score_adjustment": (\n                            research_decision.score_adjustment if research_decision is not None else 0\n                        ),\n                        "detail": detail,\n                        "decision_at": observed_at,\n                    }\n                    await self._event(\n                        strategy_repository,\n                        config,\n                        instrument_id=candidate.instrument_id,\n                        event_type="research_policy",\n                        state="entry_ready" if allowed else "rejected",\n                        reason_code=reason_code,\n                        observed_at=observed_at,\n                        payload=payload,\n                    )\n                    trade_log(\n                        "auto_trading",\n                        "research_policy_decision",\n                        run_id=self.current_run_id,\n                        strategy_id=config.strategy_id,\n                        instrument_id=candidate.instrument_id,\n                        **payload,\n                        reason_code=reason_code,\n                    )\n                    if not allowed:\n                        self.rejection_count += 1\n                        continue\n                proposals.append(\n''',
    )


def patch_backtest() -> None:
    path = "src/app/trading/strategy_backtest.py"
    replace_once(
        path,
        "import math\nfrom dataclasses import dataclass\n",
        "import math\nfrom collections.abc import Callable\nfrom dataclasses import dataclass\n",
    )
    replace_once(
        path,
        "from .strategies.gap_pullback import evaluate_gap_pullback\n",
        "from .research.policy import ResearchPolicyDecision\nfrom .strategies.gap_pullback import evaluate_gap_pullback\n",
    )
    replace_once(
        path,
        '''    risk_rejection_count: int\n    risk_rejection_reasons: dict[str, int] = Field(default_factory=dict)\n    partial_entry_count: int\n''',
        '''    risk_rejection_count: int\n    risk_rejection_reasons: dict[str, int] = Field(default_factory=dict)\n    research_rejection_count: int = 0\n    research_rejection_reasons: dict[str, int] = Field(default_factory=dict)\n    partial_entry_count: int\n''',
    )
    replace_once(
        path,
        '''    risk_profile: StrategyRiskProfile | None = None,\n    initial_cash: Decimal = Decimal("100000"),\n) -> GapPullbackBacktestResult:\n''',
        '''    risk_profile: StrategyRiskProfile | None = None,\n    initial_cash: Decimal = Decimal("100000"),\n    research_policy_resolver: Callable[[str, datetime], ResearchPolicyDecision] | None = None,\n) -> GapPullbackBacktestResult:\n''',
    )
    replace_once(
        path,
        '''    selected: list[GapPullbackBacktestTrade] = []\n    risk_rejections: dict[str, int] = {}\n    execution_rejections: list[str] = []\n    for candidate, proposal in proposed:\n        snapshot, realized, open_risk, active_symbols = _virtual_snapshot(\n''',
        '''    selected: list[GapPullbackBacktestTrade] = []\n    risk_rejections: dict[str, int] = {}\n    research_rejections: dict[str, int] = {}\n    execution_rejections: list[str] = []\n    for candidate, proposal in proposed:\n        if active.strategy_version == "1.2.0":\n            if research_policy_resolver is None:\n                research_reason = "RESEARCH_POLICY_RESOLVER_UNAVAILABLE"\n            else:\n                try:\n                    research_decision = research_policy_resolver(proposal.instrument_id, proposal.entry_time)\n                except Exception:\n                    research_reason = "RESEARCH_POLICY_RESOLUTION_ERROR"\n                else:\n                    research_reason = None if research_decision.allowed else research_decision.reason_code\n            if research_reason is not None:\n                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1\n                continue\n        snapshot, realized, open_risk, active_symbols = _virtual_snapshot(\n''',
    )
    replace_once(
        path,
        '''        risk_rejection_count=sum(risk_rejections.values()),\n        risk_rejection_reasons=risk_rejections,\n        partial_entry_count=sum(\n''',
        '''        risk_rejection_count=sum(risk_rejections.values()),\n        risk_rejection_reasons=risk_rejections,\n        research_rejection_count=sum(research_rejections.values()),\n        research_rejection_reasons=research_rejections,\n        partial_entry_count=sum(\n''',
    )


def patch_range_backtest() -> None:
    path = "src/app/trading/strategy_range_backtest.py"
    replace_once(
        path,
        "from .providers.http_runtime import ProviderHttpRuntime\n",
        "from .providers.http_runtime import ProviderHttpRuntime\nfrom .research.policy import ResearchPolicyDecision\n",
    )
    replace_once(
        path,
        '''    *,\n    reconstructor: Reconstructor = reconstruct_recent_alpaca_gapper_universe,\n) -> StrategyRangeBacktestResult:\n''',
        '''    *,\n    reconstructor: Reconstructor = reconstruct_recent_alpaca_gapper_universe,\n    research_policy_resolver: Callable[[str, datetime], ResearchPolicyDecision] | None = None,\n) -> StrategyRangeBacktestResult:\n''',
    )
    replace_once(
        path,
        '''                risk_profile=strategy.risk,\n                initial_cash=current_cash,\n            )\n''',
        '''                risk_profile=strategy.risk,\n                initial_cash=current_cash,\n                research_policy_resolver=research_policy_resolver,\n            )\n''',
    )


def patch_strategy_api() -> None:
    path = "src/app/trading/strategy_api.py"
    replace_once(
        path,
        "from .paper import PaperExecutionPolicy\n",
        "from .paper import PaperExecutionPolicy\nfrom .research.fact_repository import default_fact_repository\nfrom .research.outcome_dataset import persist_backtest_trade_outcomes\n",
    )
    replace_once(
        path,
        "from .strategy_repository import (\n",
        "from .strategy_research_policy import resolve_strategy_research_policy\nfrom .strategy_repository import (\n",
    )
    replace_once(
        path,
        '''            result = await asyncio.to_thread(\n                run_gap_pullback_backtest,\n                dataset,\n                request.config,\n                request.execution_policy,\n                assumed_spread_bps=request.assumed_spread_bps,\n                max_hold_minutes=request.max_hold_minutes,\n                max_concurrent_positions=request.max_concurrent_positions,\n                risk_profile=request.risk_profile,\n                initial_cash=request.initial_cash,\n            )\n            trade_log(\n''',
        '''            fact_repository = None\n\n            def research_policy_resolver(instrument_id: str, decision_at: datetime):\n                nonlocal fact_repository\n                if fact_repository is None:\n                    fact_repository = default_fact_repository()\n                return resolve_strategy_research_policy(\n                    strategy_version=request.config.strategy_version,\n                    instrument_id=instrument_id,\n                    decision_at=decision_at,\n                    fact_repository=fact_repository,\n                )\n\n            result = await asyncio.to_thread(\n                run_gap_pullback_backtest,\n                dataset,\n                request.config,\n                request.execution_policy,\n                assumed_spread_bps=request.assumed_spread_bps,\n                max_hold_minutes=request.max_hold_minutes,\n                max_concurrent_positions=request.max_concurrent_positions,\n                risk_profile=request.risk_profile,\n                initial_cash=request.initial_cash,\n                research_policy_resolver=research_policy_resolver,\n            )\n            try:\n                fact_repository = fact_repository or default_fact_repository()\n                captured = await asyncio.to_thread(\n                    persist_backtest_trade_outcomes,\n                    strategy_id=request.config.strategy_id,\n                    strategy_version=request.config.strategy_version,\n                    session_date=request.session_date,\n                    trades=result.trades,\n                    market_fidelity="captured_point_in_time",\n                    fact_repository=fact_repository,\n                    reward_multiple=request.config.reward_multiple,\n                )\n                trade_log("backtest", "research_outcomes_captured", run_id=run_id, count=captured)\n            except Exception as exc:\n                trade_log("backtest", "research_outcome_capture_error", run_id=run_id, error_type=type(exc).__name__, detail=str(exc))\n            trade_log(\n''',
    )
    replace_once(
        path,
        '''            result = await asyncio.to_thread(\n                run_strategy_range_backtest,\n                strategy,\n                universes,\n                request,\n            )\n            for day in result.days:\n''',
        '''            fact_repository = None\n\n            def range_research_policy_resolver(instrument_id: str, decision_at: datetime):\n                nonlocal fact_repository\n                if fact_repository is None:\n                    fact_repository = default_fact_repository()\n                return resolve_strategy_research_policy(\n                    strategy_version=strategy.config.strategy_version,\n                    instrument_id=instrument_id,\n                    decision_at=decision_at,\n                    fact_repository=fact_repository,\n                )\n\n            result = await asyncio.to_thread(\n                run_strategy_range_backtest,\n                strategy,\n                universes,\n                request,\n                research_policy_resolver=range_research_policy_resolver,\n            )\n            for day in result.days:\n''',
    )
    replace_once(
        path,
        '''                trade_log(\n                    "backtest",\n                    "range_backtest_day",\n                    run_id=run_id,\n                    strategy_id=strategy_id,\n                    day=day,\n                )\n            trade_log(\n''',
        '''                trade_log(\n                    "backtest",\n                    "range_backtest_day",\n                    run_id=run_id,\n                    strategy_id=strategy_id,\n                    day=day,\n                )\n                if day.result is not None and day.result.trades:\n                    try:\n                        fact_repository = fact_repository or default_fact_repository()\n                        captured = await asyncio.to_thread(\n                            persist_backtest_trade_outcomes,\n                            strategy_id=strategy_id,\n                            strategy_version=strategy.config.strategy_version,\n                            session_date=day.session_date,\n                            trades=day.result.trades,\n                            market_fidelity=(\n                                "captured_point_in_time" if day.universe_origin == "captured"\n                                else "reconstructed_current_listings_iex"\n                            ),\n                            fact_repository=fact_repository,\n                            reward_multiple=strategy.config.reward_multiple,\n                        )\n                        trade_log("backtest", "range_research_outcomes_captured", run_id=run_id, strategy_id=strategy_id, session_date=day.session_date, count=captured)\n                    except Exception as exc:\n                        trade_log("backtest", "research_outcome_capture_error", run_id=run_id, strategy_id=strategy_id, session_date=day.session_date, error_type=type(exc).__name__, detail=str(exc))\n            trade_log(\n''',
    )


def restore_workflow_and_remove_self() -> None:
    workflow = ROOT / ".github/workflows/trading-terminal.yml"
    text = workflow.read_text(encoding="utf-8")
    text = text.replace(
        "# TEMPORARY HTR execution parity patch for PR #1494. The patch script restores read-only.\npermissions:\n  contents: write\n",
        "permissions:\n  contents: read\n",
    )
    marker_start = "      # BEGIN TEMP HTR EXECUTION PATCH\n"
    marker_end = "      # END TEMP HTR EXECUTION PATCH\n"
    if marker_start not in text or marker_end not in text:
        raise RuntimeError("temporary HTR workflow step markers missing")
    before, rest = text.split(marker_start, 1)
    _, after = rest.split(marker_end, 1)
    workflow.write_text(before + after, encoding="utf-8")
    Path(__file__).unlink()


def main() -> None:
    patch_monitor()
    patch_backtest()
    patch_range_backtest()
    patch_strategy_api()
    restore_workflow_and_remove_self()


if __name__ == "__main__":
    main()
