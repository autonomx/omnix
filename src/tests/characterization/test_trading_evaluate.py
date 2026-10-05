from __future__ import annotations

import json
from typing import Any

from app.apps.trading.strategy_monitor import TradingStrategyMonitor
from src.tests.trading.test_trading_auto_paper_e2e_replay import (
    test_sep3_tlys_auto_paper_runtime_places_fills_and_protects_trade as _run_fixed_bar_scenario,
)
from tests.characterization.harness import capture

# The catalog modules this scenario characterizes (scripts/test_module.py).
MODULES = ("trading",)


def _proposal_record(proposal: Any) -> dict[str, Any]:
    result = proposal.result
    return {
        "instrument_id": proposal.candidate.instrument_id,
        "state": result.state,
        "reason_code": result.reason_code,
        "signal": result.signal.model_dump(mode="json") if result.signal else None,
        "observed_at": proposal.observed_at,
    }


def test_trading_evaluate_matches_pre_refactor_golden(monkeypatch) -> None:
    monitors: list[TradingStrategyMonitor] = []
    run_results: list[int] = []
    proposal_runs: list[list[dict[str, Any]]] = []

    original_init = TradingStrategyMonitor.__init__

    def capture_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        monitors.append(self)

    original_evaluate = TradingStrategyMonitor._evaluate_candidates

    async def capture_evaluate(self, *args, **kwargs):
        proposals = await original_evaluate(self, *args, **kwargs)
        proposal_runs.append([_proposal_record(proposal) for proposal in proposals])
        return proposals

    original_run_once = TradingStrategyMonitor.run_once

    async def capture_run_once(self, *args, **kwargs):
        result = await original_run_once(self, *args, **kwargs)
        run_results.append(result)
        return result

    monkeypatch.setattr(TradingStrategyMonitor, "__init__", capture_init)
    monkeypatch.setattr(TradingStrategyMonitor, "_evaluate_candidates", capture_evaluate)
    monkeypatch.setattr(TradingStrategyMonitor, "run_once", capture_run_once)

    _run_fixed_bar_scenario(monkeypatch)

    monitor = monitors[-1]
    strategy_repository = monitor.strategy_repository_factory()
    paper_repository = monitor.paper_repository_factory()
    config = strategy_repository.config
    paper_snapshot = paper_repository.snapshot(config.account_id)
    authorization_events = [
        event
        for event in strategy_repository.events
        if event.event_type == "trade_authorization"
    ]
    candidate_instrument_id = proposal_runs[0][0]["instrument_id"]
    relevant_events = [
        {
            "event_type": event.event_type,
            "state": event.state,
            "reason_code": event.reason_code,
            "instrument_id": event.instrument_id,
        }
        for event in strategy_repository.events
        if event.event_type
        in {
            "candidate_evaluation",
            "trade_authorization",
            "entry_order_submitted",
            "shadow_execution",
        }
        and event.instrument_id == candidate_instrument_id
    ]

    def scenario() -> dict[str, Any]:
        return json.loads(json.dumps({
            "proposal_runs": proposal_runs[:1],
            "run_results": run_results,
            "authorization_decisions": [
                {
                    "state": event.state,
                    "reason_code": event.reason_code,
                    "assessment": event.payload.get("assessment"),
                }
                for event in authorization_events
            ],
            "paper_orders": [
                {
                    "order_id": order.order_id,
                    "instrument_id": order.instrument_id,
                    "side": order.side,
                    "quantity": order.quantity,
                    "limit_price": order.limit_price,
                    "status": order.status,
                    "filled_quantity": order.filled_quantity,
                    "average_fill_price": order.average_fill_price,
                }
                for order in paper_snapshot.order_history
            ],
            "paper_fills": [
                {
                    "order_id": fill.order_id,
                    "instrument_id": fill.instrument_id,
                    "side": fill.side,
                    "quantity": fill.quantity,
                    "price": fill.price,
                }
                for fill in paper_snapshot.recent_fills
            ],
            "events": relevant_events,
            "protections": [
                {
                    "instrument_id": protection.instrument_id,
                    "status": protection.status,
                    "quantity": protection.quantity,
                }
                for protection in strategy_repository.list_protections(
                    config.strategy_id,
                    active_only=True,
                )
            ],
        }, default=str))

    capture("trading-evaluate", scenario)
