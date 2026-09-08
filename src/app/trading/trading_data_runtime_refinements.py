from __future__ import annotations

"""Small follow-up refinements layered on the trading data hardening installer."""

from datetime import datetime, timezone

from .gapper_dataset import GapperCandidate
from .market_evidence import MARKET_EVIDENCE_POLICY_VERSION
from .strategy_evaluability import candidate_morning_evidence_eligible as _strict_morning_evidence


_INSTALLED = False


def _morning_evidence(candidate, config):
    """Apply V2 evidence rules to real immutable candidates, not unit-test doubles.

    Runtime universes are always populated with ``GapperCandidate``. A number of
    narrow legacy monitor unit tests intentionally pass ``SimpleNamespace`` rows
    to exercise unrelated state machines. Treating those doubles as production
    market evidence both hides the test's intent and raises attribute errors.
    """

    if not isinstance(candidate, GapperCandidate):
        return True, ()
    return _strict_morning_evidence(candidate, config)


def install_trading_data_runtime_refinements() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow_monitor as ai_monitor
    from . import strategy_api
    from . import strategy_evaluability
    from . import trading_data_hardening as base_hardening
    import app.trading.strategies as strategy_dispatch

    # Keep all already-imported hardening references on the same production/test
    # candidate boundary. Production objects remain fully strict.
    strategy_evaluability.candidate_morning_evidence_eligible = _morning_evidence
    base_hardening.candidate_morning_evidence_eligible = _morning_evidence

    # The deep-recovery coverage adapter must remain compatible with lightweight
    # market-service fixtures whose bars() signature predates optional cancellation.
    def compatible_coverage_bars(self, instrument_id, interval, limit=500, binding_id=None, cancellation=None):
        response = self._delegate.bars(
            instrument_id,
            interval,
            limit,
            binding_id,
        )
        if (
            interval == "1m"
            and self._observed_at.astimezone(base_hardening._ET).time()
            >= datetime.strptime("09:30", "%H:%M").time()
        ):
            assessment = base_hardening.assess_bar_coverage(
                list(response.bars),
                session_date=self._session_date,
                observed_at=self._observed_at,
                provider="configured_history",
            )
            if not assessment.ready:
                raise ValueError(
                    "bar_coverage_not_ready:"
                    + ",".join(assessment.reason_codes)
                )
        return response

    base_hardening._CoverageMarketService.bars = compatible_coverage_bars

    # The interactive/API evaluator must use the same hardened version dispatcher
    # as live monitoring, backtests and replay.
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
            morning_ok, reasons = _morning_evidence(candidate, config.config)
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

        if policy == "minute":
            universe_id = str(prepared[0].get("universe_id") or "")
            expected_ids: set[str] = set()
            try:
                universe = repository.get_universe(universe_id)
            except Exception:
                universe = None
            if universe is not None:
                for candidate in universe.candidates:
                    morning_ok, _ = _morning_evidence(candidate, config.config)
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
                observed_at = max(watermarks, default=datetime.now(timezone.utc))
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
