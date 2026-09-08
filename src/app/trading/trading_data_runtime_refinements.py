from __future__ import annotations

"""Small follow-up refinements layered on the trading data hardening installer."""

from datetime import timezone

from .strategy_evaluability import candidate_morning_evidence_eligible


_INSTALLED = False


def install_trading_data_runtime_refinements() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow_monitor as ai_monitor

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
                    "morning_evidence_reason_codes": list(reasons),
                    "research_only": True,
                    "execution_authority": False,
                },
                identity=(
                    policy,
                    observed_at.astimezone(timezone.utc).isoformat(),
                    "morning_evidence",
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

        # The every-minute arm is a cohort experiment. Do not emit fragmented
        # batches when symbols have not yet converged on one finalized minute.
        # A subsequent poll will run once the common watermark is available.
        if policy == "minute":
            watermarks = {
                row["observed_at"].astimezone(timezone.utc)
                for row in prepared
            }
            if len(watermarks) != 1:
                observed_at = max(watermarks)
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
                        "candidate_count": len(prepared),
                        "candidate_watermarks": sorted(
                            item.isoformat() for item in watermarks
                        ),
                        "research_only": True,
                        "execution_authority": False,
                    },
                    identity=(
                        policy,
                        observed_at.isoformat(),
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
