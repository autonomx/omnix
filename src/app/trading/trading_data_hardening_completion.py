from __future__ import annotations

"""Final integration hooks for market-evidence-v2.

This module is intentionally small and is installed after ``trading_data_hardening``.
It closes two remaining orchestration gaps without changing execution authority:

* the AI minute arm waits for the complete eligible cohort to share one finalized
  minute watermark before any model call; and
* candidates whose frozen morning evidence is ineligible become typed input-gap
  events rather than model decisions.

It also routes the strategy API through the same V2 dispatcher already installed
for runtime/backtest/replay paths.
"""

from datetime import datetime, timezone

from .market_evidence import MARKET_EVIDENCE_POLICY_VERSION
from .strategy_evaluability import candidate_morning_evidence_eligible


_INSTALLED = False


def install_trading_data_hardening_completion() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow_monitor as ai_monitor
    from . import strategy_api
    from . import trading_data_hardening as base
    import app.trading.strategies as strategy_dispatch

    # Interactive/API evaluation must use the same version dispatcher as live,
    # replay and backtest paths. The base installer has already hardened it.
    strategy_api.evaluate_gap_pullback = strategy_dispatch.evaluate_gap_pullback

    original_run_policy = ai_monitor.TradingAIShadowMonitor._run_policy

    async def completed_run_policy(
        self,
        *,
        policy,
        rows,
        config,
        repository,
        market_service,
        events,
    ):
        eligible_rows = []
        for row in rows:
            candidate = row["candidate"]
            observed_at = row["observed_at"]
            assert isinstance(observed_at, datetime)
            morning_ok, morning_reasons = candidate_morning_evidence_eligible(
                candidate,
                config.config,
            )
            if morning_ok:
                eligible_rows.append(row)
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
                    "morning_evidence_reason_codes": list(morning_reasons),
                    "research_only": True,
                    "execution_authority": False,
                },
                identity=(
                    policy,
                    observed_at.astimezone(timezone.utc).isoformat(),
                    "morning-evidence",
                    *morning_reasons,
                ),
            )
            if persisted:
                self.data_gap_count += 1

        if not eligible_rows:
            return

        if policy == "minute":
            universe_id = str(eligible_rows[0].get("universe_id") or "")
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

            row_ids = {row["candidate"].instrument_id for row in eligible_rows}
            observed_by_id = {
                row["candidate"].instrument_id: row["observed_at"]
                for row in eligible_rows
            }
            watermark_values = {
                observed.astimezone(timezone.utc)
                for observed in observed_by_id.values()
                if isinstance(observed, datetime)
            }
            cohort_complete = not expected_ids or row_ids == expected_ids
            watermark_ready = len(watermark_values) == 1
            if not cohort_complete or not watermark_ready:
                gap_at = max(
                    (
                        observed.astimezone(timezone.utc)
                        for observed in observed_by_id.values()
                        if isinstance(observed, datetime)
                    ),
                    default=datetime.now(timezone.utc),
                )
                persisted = await self._append(
                    repository,
                    config,
                    instrument_id="__universe__",
                    event_type="ai_shadow_input_gap",
                    state="waiting",
                    reason_code="AI_SHADOW_COMMON_MINUTE_NOT_READY",
                    observed_at=gap_at,
                    payload={
                        "policy": policy,
                        "universe_id": universe_id or None,
                        "expected_instrument_ids": sorted(expected_ids),
                        "available_instrument_ids": sorted(row_ids),
                        "observed_at_by_instrument": {
                            instrument_id: observed.astimezone(timezone.utc).isoformat()
                            for instrument_id, observed in sorted(observed_by_id.items())
                            if isinstance(observed, datetime)
                        },
                        "cohort_complete": cohort_complete,
                        "common_finalized_minute": watermark_ready,
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
                                    observed.astimezone(timezone.utc).isoformat(),
                                )
                                for instrument_id, observed in observed_by_id.items()
                                if isinstance(observed, datetime)
                            )
                        ),
                        "common-minute",
                    ),
                )
                if persisted:
                    self.data_gap_count += 1
                return

        return await original_run_policy(
            self,
            policy=policy,
            rows=eligible_rows,
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )

    ai_monitor.TradingAIShadowMonitor._run_policy = completed_run_policy
    _INSTALLED = True


__all__ = ["install_trading_data_hardening_completion"]
