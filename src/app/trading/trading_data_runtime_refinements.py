from __future__ import annotations

"""Small follow-up refinements layered on the trading data hardening installer."""

from datetime import datetime, timezone

from .market_evidence import MARKET_EVIDENCE_POLICY_VERSION
from .strategy_evaluability import candidate_morning_evidence_eligible


_INSTALLED = False


def install_trading_data_runtime_refinements() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow_monitor as ai_monitor
    from . import strategy_api
    import app.trading.strategies as strategy_dispatch

    # The interactive/API evaluator must use the same hardened version dispatcher
    # as live monitoring, backtests and replay. This closes the final direct-import
    # path that could otherwise evaluate a 2.0.0 profile with 1.x semantics.
    strategy_api.evaluate_gap_pullback = strategy_dispatch.evaluate_gap_pullback

    previous_run_policy = ai_monitor.TradingAIShadowMonitor._run_policy

    async def refined_run_policy(
        self,
        *,
        policy,
        rows,
        config,
        repository,
        market_service,
        events,
    ):
        prepared = []
        for row in rows:
            candidate = row["candidate"]
            observed_at = row["observed_at"]
            assert isinstance(observed_at, datetime)
            morning_ok, reasons = candidate_morning_evidence_eligible(
                candidate,
                config.config,
            )
            if morning_ok:
                prepared.append(row)
                continue
            persisted = await self._append(
                repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="ai_shadow_input_gap",
                state="unavailable",
                reason_code="AI_SHADOW_MORNING_EVIDENCE_GAP",
                observed_at=observed_at,
                payload={
                    "policy": policy,
                    "universe_id": row.get("universe_id"),
                    "market_evidence_policy_version": MARKET_EVIDENCE_POLICY_VERSION,
                    "morning_evidence_reason_codes": list(reasons),
                    "research_only": True,
                    "execution_authority": False,
                },
                identity=(
                    policy,
                    observed_at.astimezone(timezone.utc).isoformat(),
                    "morning_evidence",
                    *reasons,
                ),
            )
            if persisted:
                self.data_gap_count += 1
            ai_monitor.trade_log(
                "auto_trading",
                "ai_shadow_input_gap",
                strategy_id=config.strategy_id,
                policy=policy,
                instrument_id=candidate.instrument_id,
                reason_code="AI_SHADOW_MORNING_EVIDENCE_GAP",
                morning_evidence_reason_codes=list(reasons),
                execution_authority=False,
            )

        if not prepared:
            return

        # The every-minute arm is a cohort experiment. It must not emit a model
        # batch until every morning-eligible member that belongs to this immutable
        # universe has a row and every one of those rows terminates at the exact
        # same finalized minute. Missing members are therefore input gaps, not a
        # smaller survivor cohort.
        if policy == "minute":
            universe_id = str(prepared[0].get("universe_id") or "")
            expected_ids: set[str] = set()
            try:
                universe = repository.get_universe(universe_id)
            except Exception:
                universe = None
            if universe is not None:
                for candidate in universe.candidates:
                    morning_ok, _ = candidate_morning_evidence_eligible(
                        candidate,
                        config.config,
                    )
                    if morning_ok:
                        expected_ids.add(candidate.instrument_id)

            row_ids = {row["candidate"].instrument_id for row in prepared}
            observed_by_id = {
                row["candidate"].instrument_id: row["observed_at"]
                for row in prepared
            }
            watermarks = {
                observed.astimezone(timezone.utc)
                for observed in observed_by_id.values()
                if isinstance(observed, datetime)
            }
            cohort_complete = not expected_ids or row_ids == expected_ids
            common_watermark = len(watermarks) == 1
            if not cohort_complete or not common_watermark:
                observed_at = max(
                    watermarks,
                    default=datetime.now(timezone.utc),
                )
                persisted = await self._append(
                    repository,
                    config,
                    instrument_id="__universe__",
                    event_type="ai_shadow_input_gap",
                    state="pending",
                    reason_code="AI_SHADOW_COHORT_WATERMARK_PENDING",
                    observed_at=observed_at,
                    payload={
                        "policy": policy,
                        "universe_id": universe_id or None,
                        "expected_instrument_ids": sorted(expected_ids),
                        "available_instrument_ids": sorted(row_ids),
                        "cohort_complete": cohort_complete,
                        "common_finalized_minute": common_watermark,
                        "candidate_watermarks": {
                            instrument_id: value.astimezone(timezone.utc).isoformat()
                            for instrument_id, value in sorted(observed_by_id.items())
                            if isinstance(value, datetime)
                        },
                        "research_only": True,
                        "execution_authority": False,
                    },
                    identity=(
                        policy,
                        universe_id,
                        tuple(sorted(expected_ids)),
                        tuple(
                            sorted(
                                (
                                    instrument_id,
                                    value.astimezone(timezone.utc).isoformat(),
                                )
                                for instrument_id, value in observed_by_id.items()
                                if isinstance(value, datetime)
                            )
                        ),
                        "cohort_watermark_pending",
                    ),
                )
                if persisted:
                    self.data_gap_count += 1
                return

        return await previous_run_policy(
            self,
            policy=policy,
            rows=prepared,
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )

    ai_monitor.TradingAIShadowMonitor._run_policy = refined_run_policy
    _INSTALLED = True


__all__ = ["install_trading_data_runtime_refinements"]
