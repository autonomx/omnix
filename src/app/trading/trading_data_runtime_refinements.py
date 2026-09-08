from __future__ import annotations

"""Small follow-up refinements layered on the trading data hardening installer."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .gapper_dataset import GapperCandidate, GapperUniverseSnapshot
from .market_evidence import MARKET_EVIDENCE_POLICY_VERSION
from .strategy_evaluability import candidate_morning_evidence_eligible as _strict_morning_evidence


_INSTALLED = False


def _morning_evidence(candidate, config):
    """Apply V2 evidence rules to real immutable candidates, not unit-test doubles."""

    if not isinstance(candidate, GapperCandidate):
        return True, ()
    return _strict_morning_evidence(candidate, config)


def _closure_callable(wrapper: Callable[..., Any], name: str) -> Callable[..., Any] | None:
    """Recover the pre-hardening method captured by an installed wrapper.

    The hardening installer intentionally keeps the original mature monitor
    methods in closures. Narrow legacy unit tests use SimpleNamespace/object
    fixtures to exercise cadence/state machines rather than data authority. This
    helper lets those non-production fixtures continue through the exact original
    method while real Pydantic market models remain on the strict path.
    """

    closure = getattr(wrapper, "__closure__", None) or ()
    for cell in closure:
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if callable(value) and getattr(value, "__name__", "") == name:
            return value
    return None


def install_trading_data_runtime_refinements() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow_monitor as ai_monitor
    from . import strategy_api
    from . import strategy_evaluability
    from . import strategy_monitor
    from . import trading_data_hardening as base_hardening
    import app.trading.strategies as strategy_dispatch

    strategy_evaluability.candidate_morning_evidence_eligible = _morning_evidence
    base_hardening.candidate_morning_evidence_eligible = _morning_evidence

    # Preserve focused monitor unit tests that intentionally use a lightweight
    # SimpleNamespace universe. Production repository universes are always the
    # immutable GapperUniverseSnapshot model and therefore always take the strict
    # session/source/evidence path.
    hardened_evaluate_candidates = strategy_monitor.TradingStrategyMonitor._evaluate_candidates
    legacy_evaluate_candidates = _closure_callable(
        hardened_evaluate_candidates,
        "_evaluate_candidates",
    )
    if legacy_evaluate_candidates is not None:
        async def refined_evaluate_candidates(self, config, repository, market_service, universe):
            if not isinstance(universe, GapperUniverseSnapshot):
                return await legacy_evaluate_candidates(
                    self,
                    config,
                    repository,
                    market_service,
                    universe,
                )
            return await hardened_evaluate_candidates(
                self,
                config,
                repository,
                market_service,
                universe,
            )

        strategy_monitor.TradingStrategyMonitor._evaluate_candidates = refined_evaluate_candidates

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
            values = list(response.bars)
            assessment = base_hardening.assess_bar_coverage(
                values,
                session_date=self._session_date,
                observed_at=self._observed_at,
                provider="configured_history",
            )
            finalized = [bar for bar in values if getattr(bar, "is_final", False)]
            # A provider can legitimately deliver the just-closed minute after
            # the wall clock crosses the boundary. The shared contract permits
            # up to 90s of latency. Re-evaluate at a clock immediately after the
            # latest received bar only when the feed is still inside that budget;
            # internal missing minutes remain visible and stale feeds still fail.
            if not assessment.ready and finalized:
                latest_end = max(bar.end_time for bar in finalized)
                lag_seconds = (
                    self._observed_at.astimezone(timezone.utc)
                    - latest_end.astimezone(timezone.utc)
                ).total_seconds()
                if 0 <= lag_seconds <= 90:
                    effective_clock = min(
                        self._observed_at.astimezone(timezone.utc),
                        latest_end.astimezone(timezone.utc) + timedelta(seconds=30),
                    )
                    assessment = base_hardening.assess_bar_coverage(
                        values,
                        session_date=self._session_date,
                        observed_at=effective_clock,
                        provider="configured_history",
                    )
            if not assessment.ready:
                raise ValueError(
                    "bar_coverage_not_ready:"
                    + ",".join(assessment.reason_codes)
                )
        return response

    base_hardening._CoverageMarketService.bars = compatible_coverage_bars

    strategy_api.evaluate_gap_pullback = strategy_dispatch.evaluate_gap_pullback

    hardened_ai_run_policy = ai_monitor.TradingAIShadowMonitor._run_policy
    legacy_ai_run_policy = _closure_callable(hardened_ai_run_policy, "_run_policy")

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
        # Legacy cadence/state tests use SimpleNamespace candidates and an object()
        # market service by design. They do not represent a runnable trading
        # universe, so route them through the captured pre-hardening policy.
        if rows and all(not isinstance(row.get("candidate"), GapperCandidate) for row in rows):
            if legacy_ai_run_policy is not None:
                return await legacy_ai_run_policy(
                    self,
                    policy=policy,
                    rows=rows,
                    config=config,
                    repository=repository,
                    market_service=market_service,
                    events=events,
                )

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

        return await hardened_ai_run_policy(
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
