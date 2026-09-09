from __future__ import annotations

"""Runtime enforcement for the market-evidence-v2 trading contract.

The large strategy monitors predate the new evidence model. This installer keeps
those stable orchestration surfaces intact while replacing only authority and
readiness boundaries: V2 dispatch, bar coverage, diagnostic-only incomplete-data
analysis, strategy entry authorization, and AI input-gap semantics.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .market_evidence import (
    DEFAULT_MARKET_EVIDENCE_POLICY,
    ExecutionInputGap,
    MARKET_EVIDENCE_POLICY_VERSION,
    classify_provider_exception,
)
from .strategy_evaluability import (
    assess_bar_coverage,
    assess_session_evaluability,
    build_trade_authorization,
    candidate_morning_evidence_eligible,
    finviz_membership_only_mode,
    resolve_causal_equity_bars,
    source_member_valid,
)


_ET = ZoneInfo("America/New_York")
_INSTALLED = False


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _diagnostic_v2_candidate(candidate, config):
    """Build a non-authoritative candidate copy that bypasses morning gates only."""

    return candidate.model_copy(
        update={
            "market_data_complete": True,
            "data_quality_flags": (),
            "premarket_dollar_volume": max(
                candidate.premarket_dollar_volume,
                config.minimum_premarket_dollar_volume,
            ),
            "tod_rvol": max(
                candidate.tod_rvol or Decimal("0"),
                config.minimum_tod_rvol,
            ),
            # Frozen spread is never execution authority in market-evidence-v2.
            "spread_bps": Decimal("0"),
        }
    )


def _diagnostic_v2_config(candidate, config):
    return config.model_copy(
        update={
            "minimum_gap_pct": min(config.minimum_gap_pct, candidate.gap_pct),
            "minimum_price": min(config.minimum_price, candidate.premarket_price),
            "maximum_price": max(config.maximum_price, candidate.premarket_price),
            "minimum_premarket_dollar_volume": Decimal("0"),
            "minimum_tod_rvol": Decimal("0"),
            "maximum_spread_bps": max(config.maximum_spread_bps, Decimal("100000")),
            "require_catalyst_evidence": False,
            "reject_dilution_flags": (),
            "float_preference_mode": "ignore",
        }
    )


def _event_payload_readiness(readiness) -> dict[str, object]:
    return readiness.model_dump(mode="json")


class _AuthorizedStrategyPaperRepository:
    """Pass-through repository that proves authority immediately before a buy."""

    def __init__(
        self,
        *,
        delegate,
        monitor,
        config,
        strategy_repository,
        market_service,
        monitor_module,
        qualification_module,
    ) -> None:
        self._delegate = delegate
        self._monitor = monitor
        self._config = config
        self._strategy_repository = strategy_repository
        self._market_service = market_service
        self._monitor_module = monitor_module
        self._qualification_module = qualification_module

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def _events(self):
        return self._strategy_repository.recent_events(
            self._config.strategy_id,
            20_000,
        )

    def _persist_authorization(self, assessment, *, observed_at: datetime, payload: dict[str, object]) -> None:
        from .strategy_repository import StrategyEvent

        idem = _key(
            assessment.strategy_id,
            assessment.trade_attempt_id,
            assessment.policy_version,
            assessment.authorized,
        )
        self._strategy_repository.append_event(
            StrategyEvent(
                strategy_id=assessment.strategy_id,
                event_id=idem[:32],
                run_id=self._monitor.current_run_id,
                instrument_id=assessment.instrument_id,
                event_type="trade_authorization",
                state="authorized" if assessment.authorized else "denied",
                reason_code=(
                    "TRADE_AUTHORIZATION_APPROVED"
                    if assessment.authorized
                    else "TRADE_AUTHORIZATION_DENIED"
                ),
                observed_at=observed_at,
                idempotency_key=idem,
                payload={
                    **payload,
                    "assessment": assessment.model_dump(mode="json"),
                    "execution_authority": assessment.authorized,
                },
            )
        )

    def place_order(self, account_id: str, request):
        # Protective/force-flat sells preserve their existing independent safety
        # boundary. The new authorization contract guards strategy entry buys.
        if getattr(request, "side", None) != "buy":
            return self._delegate.place_order(account_id, request)

        now = datetime.now(timezone.utc)
        events = self._events()
        risk_events = [
            event
            for event in events
            if event.event_type == "risk_decision"
            and event.instrument_id == request.instrument_id
            and isinstance(event.payload, dict)
            and event.payload.get("trade_attempt_id")
        ]
        risk_event = max(
            risk_events,
            key=lambda event: (event.observed_at, event.event_id),
            default=None,
        )
        trade_attempt_id = (
            str(risk_event.payload.get("trade_attempt_id"))
            if risk_event is not None
            else f"missing-{request.order_id}"
        )
        universe_id = (
            str(risk_event.payload.get("universe_id"))
            if risk_event is not None and risk_event.payload.get("universe_id")
            else "missing-universe"
        )
        current_profile = (
            self._qualification_module.v2_profile_fingerprint(self._config.config)
            if self._config.config.strategy_version == "2.0.0"
            else self._config.config.strategy_version
        )

        universe = None
        candidate = None
        if universe_id != "missing-universe":
            try:
                universe = self._strategy_repository.get_universe(universe_id)
            except Exception:
                universe = None
        if universe is not None:
            candidate = next(
                (
                    item
                    for item in universe.candidates
                    if item.instrument_id == request.instrument_id
                ),
                None,
            )

        source_valid = False
        morning_eligible = False
        morning_reasons: tuple[str, ...] = ("CANDIDATE_MISSING",)
        session_complete = False
        session_payload: dict[str, object] | None = None
        coverage = None
        if universe is not None and candidate is not None:
            source_valid = source_member_valid(universe, candidate)
            morning_eligible, morning_reasons = candidate_morning_evidence_eligible(
                candidate,
                self._config.config,
            )
            session_assessment = assess_session_evaluability(
                universe,
                self._config.config,
            )
            session_complete = session_assessment.status == "complete"
            session_payload = session_assessment.model_dump(mode="json")
            _, coverage, _ = resolve_causal_equity_bars(
                self._market_service,
                candidate,
                session_date=universe.session_date,
                observed_at=now,
                allow_shadow_fallback=False,
            )

        execution = None
        provider_readiness = None
        if candidate is not None:
            try:
                execution = self._market_service.execution_observation(
                    candidate.instrument_id,
                    candidate.binding_id,
                )
            except Exception as exc:
                provider_readiness = classify_provider_exception(
                    exc,
                    provider=DEFAULT_MARKET_EVIDENCE_POLICY.execution_provider,
                    observed_at=now,
                )
        provider_ready = (
            execution is not None
            and getattr(execution, "provider", None)
            == DEFAULT_MARKET_EVIDENCE_POLICY.execution_provider
        )
        provider_circuit_clear = provider_ready
        execution_eligible = bool(
            execution is not None
            and getattr(execution, "execution_eligible", False)
            and getattr(execution, "spread_bps", None) is not None
            and getattr(execution, "spread_bps") <= self._config.risk.max_spread_bps
        )

        risk_payload = (
            risk_event.payload.get("risk_decision")
            if risk_event is not None and isinstance(risk_event.payload, dict)
            else None
        )
        risk_valid = bool(isinstance(risk_payload, dict) and risk_payload.get("allowed") is True)
        state_events = [
            event
            for event in events
            if event.event_type == "state"
            and event.instrument_id == request.instrument_id
            and event.state == "entry_ready"
            and isinstance(event.payload, dict)
            and event.payload.get("universe_id") == universe_id
        ]
        strategy_entry_ready = bool(state_events)
        risk_profile = (
            str(risk_event.payload.get("profile_fingerprint"))
            if risk_event is not None
            and isinstance(risk_event.payload, dict)
            and risk_event.payload.get("profile_fingerprint")
            else None
        )
        profile_matches = risk_profile == current_profile
        membership_only = bool(
            candidate is not None
            and universe is not None
            and universe.discovery_source == "finviz"
            and finviz_membership_only_mode(self._config.config)
        )
        evidence_policy_matches = bool(
            membership_only
            or (
                candidate is not None
                and getattr(candidate, "market_evidence_policy_version", None)
                == MARKET_EVIDENCE_POLICY_VERSION
            )
        )

        now_et = now.astimezone(_ET).time()
        entry_start = getattr(
            self._config.risk,
            "entry_start_et",
            self._config.config.entry_start_et,
        )
        last_entry = getattr(
            self._config.risk,
            "last_entry_et",
            self._config.config.last_entry_et,
        )
        session_open = entry_start <= now_et <= last_entry
        kill_switch_clear = not self._config.risk.kill_switch

        qualification_authorized = True
        qualification_payload: dict[str, object] | None = None
        if self._config.config.strategy_version == "2.0.0":
            qualification_events = self._monitor_module._v2_qualification_events(
                self._strategy_repository,
                self._config.strategy_id,
                now=now,
            )
            qualification = self._qualification_module.evaluate_v2_prospective_qualification(
                self._config,
                qualification_events,
            )
            qualification_authorized = qualification.auto_paper_authorized
            qualification_payload = qualification.model_dump(mode="json")

        assessment = build_trade_authorization(
            strategy_id=self._config.strategy_id,
            instrument_id=request.instrument_id,
            trade_attempt_id=trade_attempt_id,
            universe_id=universe_id,
            strategy_profile_fingerprint=current_profile,
            source_member_valid_value=source_valid,
            morning_evidence_eligible=morning_eligible,
            session_evaluability_complete=session_complete,
            bar_coverage_ready=bool(coverage is not None and coverage.ready),
            strategy_entry_ready=strategy_entry_ready,
            execution_observation_present=execution is not None,
            execution_eligible=execution_eligible,
            risk_sizing_valid=risk_valid,
            session_open=session_open,
            provider_ready=provider_ready,
            provider_circuit_clear=provider_circuit_clear,
            strategy_kill_switch_clear=kill_switch_clear,
            qualification_authorized=qualification_authorized,
            profile_matches=profile_matches,
            evidence_policy_matches=evidence_policy_matches,
        )
        payload = {
            "order_id": request.order_id,
            "account_id": account_id,
            "morning_evidence_reason_codes": list(morning_reasons),
            "session_evaluability": session_payload,
            "bar_coverage": coverage.model_dump(mode="json") if coverage is not None else None,
            "provider_readiness": (
                _event_payload_readiness(provider_readiness)
                if provider_readiness is not None
                else {
                    "provider": getattr(execution, "provider", None),
                    "state": "READY" if provider_ready else "UNKNOWN_ERROR",
                    "ready": provider_ready,
                    "observed_at": now.isoformat(),
                }
            ),
            "fresh_execution": (
                self._monitor_module._execution_audit_payload(execution)
                if execution is not None
                else None
            ),
            "risk_decision": risk_payload,
            "qualification": qualification_payload,
        }
        self._persist_authorization(assessment, observed_at=now, payload=payload)
        if not assessment.authorized:
            raise ValueError(
                "trade_authorization_denied:"
                + ",".join(assessment.reason_codes)
            )
        return self._delegate.place_order(account_id, request)


class _CoverageMarketService:
    def __init__(self, delegate, *, session_date, observed_at) -> None:
        self._delegate = delegate
        self._session_date = session_date
        self._observed_at = observed_at

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def bars(self, instrument_id, interval, limit=500, binding_id=None, cancellation=None):
        response = self._delegate.bars(
            instrument_id,
            interval,
            limit,
            binding_id,
            cancellation,
        )
        if interval == "1m" and self._observed_at.astimezone(_ET).time() >= datetime.strptime("09:30", "%H:%M").time():
            assessment = assess_bar_coverage(
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


def install_trading_data_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow as ai_shadow
    from . import strategy_ai_shadow_monitor as ai_monitor
    from . import strategy_backtest
    from . import strategy_causal_replay
    from . import strategy_deep_recovery_monitor
    from . import strategy_monitor
    from . import strategy_v2_qualification as qualification
    from .strategies import failed_selloff_v2
    from .strategies import gap_pullback as v1_module
    from .strategies import models as strategy_models
    import app.trading.strategies as strategy_dispatch_module

    original_v1 = v1_module.evaluate_gap_pullback
    original_v2 = failed_selloff_v2.evaluate_gap_pullback_v2

    def hardened_dispatch(candidate, bars, config=None):
        active = config or strategy_models.GapPullbackConfig()
        if active.strategy_version != "2.0.0":
            return original_v1(candidate, bars, active)
        adjusted = candidate
        if candidate.spread_bps is None or candidate.spread_bps > active.maximum_spread_bps:
            adjusted = candidate.model_copy(update={"spread_bps": Decimal("0")})
        result = original_v2(adjusted, bars, active)
        if adjusted is not candidate:
            result = result.model_copy(
                update={
                    "features": result.features.model_copy(
                        update={"spread_bps": candidate.spread_bps}
                    )
                }
            )
        return result

    # One canonical dispatcher everywhere V2 can be evaluated. Several legacy
    # modules imported the 1.x function directly, bypassing strategies.__init__.
    v1_module.evaluate_gap_pullback = hardened_dispatch
    failed_selloff_v2.evaluate_gap_pullback_v2 = hardened_dispatch
    strategy_dispatch_module.evaluate_gap_pullback = hardened_dispatch
    strategy_monitor.evaluate_gap_pullback = hardened_dispatch
    strategy_backtest.evaluate_gap_pullback = hardened_dispatch
    strategy_causal_replay.evaluate_gap_pullback = hardened_dispatch

    original_integrity = strategy_monitor._current_session_1m_integrity

    def hardened_current_session_integrity(bars, *, session_date, observed_at):
        assessment = assess_bar_coverage(
            list(bars),
            session_date=session_date,
            observed_at=observed_at,
            provider="configured_history",
        )
        if assessment.ready:
            return True, "CURRENT_SESSION_1M_READY"
        return False, assessment.reason_codes[0] if assessment.reason_codes else "CURRENT_SESSION_1M_UNAVAILABLE"

    strategy_monitor._current_session_1m_integrity = hardened_current_session_integrity

    original_evaluate_candidates = strategy_monitor.TradingStrategyMonitor._evaluate_candidates

    async def hardened_evaluate_candidates(self, config, repository, market_service, universe):
        session_assessment = assess_session_evaluability(universe, config.config)
        await self._event(
            repository,
            config,
            instrument_id="__universe__",
            event_type="session_evaluability",
            state=session_assessment.status,
            reason_code="SESSION_EVALUABILITY_ASSESSED",
            observed_at=universe.evaluation_time,
            payload={
                **session_assessment.model_dump(mode="json"),
                "market_evidence_policy_version": MARKET_EVIDENCE_POLICY_VERSION,
                "research_only": True,
                "execution_authority": False,
            },
        )
        proposals = await original_evaluate_candidates(
            self,
            config,
            repository,
            market_service,
            universe,
        )

        if config.config.strategy_version != "2.0.0" or config.mode != "shadow":
            return proposals

        for candidate in universe.candidates:
            morning_ok, morning_reasons = candidate_morning_evidence_eligible(
                candidate,
                config.config,
            )
            if morning_ok:
                continue
            now = datetime.now(timezone.utc)
            bars, coverage, primary_error = await __import__("asyncio").to_thread(
                resolve_causal_equity_bars,
                market_service,
                candidate,
                session_date=universe.session_date,
                observed_at=now,
                allow_shadow_fallback=True,
            )
            if not coverage.ready:
                continue
            diagnostic_candidate = _diagnostic_v2_candidate(candidate, config.config)
            diagnostic_config = _diagnostic_v2_config(candidate, config.config)
            structure = strategy_monitor.resample_final_bars(
                bars,
                diagnostic_config.structure_interval,
            )
            if not structure:
                continue
            result = original_v2(
                diagnostic_candidate,
                structure,
                diagnostic_config,
            )
            result = result.model_copy(
                update={
                    "features": result.features.model_copy(
                        update={
                            "spread_bps": candidate.spread_bps,
                            "tod_rvol": candidate.tod_rvol,
                        }
                    )
                }
            )
            observed_at = structure[-1].end_time
            persisted = await self._event(
                repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="diagnostic_state",
                state=result.state,
                reason_code=result.reason_code,
                observed_at=observed_at,
                payload={
                    "universe_id": universe.universe_id,
                    "qualification_eligible": False,
                    "morning_evidence_reason_codes": list(morning_reasons),
                    "bar_coverage": coverage.model_dump(mode="json"),
                    "primary_bar_error": primary_error,
                    "features": result.features.model_dump(mode="json"),
                    "transitions": list(result.transitions),
                    "signal": result.signal.model_dump(mode="json") if result.signal else None,
                    "research_only": True,
                    "execution_authority": False,
                },
            )
            if persisted:
                self.diagnostic_evaluation_count = getattr(self, "diagnostic_evaluation_count", 0) + 1
        return proposals

    strategy_monitor.TradingStrategyMonitor._evaluate_candidates = hardened_evaluate_candidates

    original_run_config = strategy_monitor.TradingStrategyMonitor._run_config

    async def hardened_run_config(self, config, strategy_repository, paper_repository, market_service):
        guarded = _AuthorizedStrategyPaperRepository(
            delegate=paper_repository,
            monitor=self,
            config=config,
            strategy_repository=strategy_repository,
            market_service=market_service,
            monitor_module=strategy_monitor,
            qualification_module=qualification,
        )
        return await original_run_config(
            self,
            config,
            strategy_repository,
            guarded,
            market_service,
        )

    strategy_monitor.TradingStrategyMonitor._run_config = hardened_run_config

    original_event_trigger_reasons = ai_shadow.event_trigger_reasons

    def hardened_event_trigger_reasons(current, previous, *, prior_decision=None):
        reasons = original_event_trigger_reasons(
            current,
            previous,
            prior_decision=prior_decision,
        )
        if not reasons or previous is None:
            return reasons
        hard = {
            "execution_eligibility_changed",
            "halt_state_changed",
            "position_state_changed",
            "thesis_invalidation_reached",
        }
        if any(reason in hard for reason in reasons):
            return reasons
        try:
            current_at = datetime.fromisoformat(str(current.get("observed_at")).replace("Z", "+00:00"))
            previous_at = datetime.fromisoformat(str(previous.get("observed_at")).replace("Z", "+00:00"))
        except Exception:
            return reasons
        if current_at.tzinfo is None or previous_at.tzinfo is None:
            return reasons
        if current_at - previous_at < timedelta(minutes=2):
            return ()
        return reasons

    ai_shadow.event_trigger_reasons = hardened_event_trigger_reasons
    ai_monitor.event_trigger_reasons = hardened_event_trigger_reasons
    if "ai_shadow_input_gap" not in ai_monitor._EVENT_TYPES:
        ai_monitor._EVENT_TYPES = (*ai_monitor._EVENT_TYPES, "ai_shadow_input_gap")

    original_ai_run_policy = ai_monitor.TradingAIShadowMonitor._run_policy

    async def hardened_ai_run_policy(self, *, policy, rows, config, repository, market_service, events):
        valid_rows = []
        for row in rows:
            candidate = row["candidate"]
            observed_at = row["observed_at"]
            feature = row.get("feature_snapshot") or {}
            execution = feature.get("execution") if isinstance(feature, dict) else None
            rejection_reasons = (
                execution.get("rejection_reasons")
                if isinstance(execution, dict)
                else []
            ) or []
            missing_execution = (
                "EXECUTION_OBSERVATION_UNAVAILABLE" in rejection_reasons
                or not isinstance(execution, dict)
                or execution.get("bid") is None
                or execution.get("ask") is None
            )
            coverage = assess_bar_coverage(
                list(row.get("bars") or []),
                session_date=observed_at.astimezone(_ET).date(),
                observed_at=observed_at,
                provider="configured_history",
            )
            if not missing_execution and coverage.ready:
                valid_rows.append(row)
                continue

            readiness = None
            if missing_execution:
                try:
                    market_service.execution_observation(
                        candidate.instrument_id,
                        candidate.binding_id,
                    )
                except Exception as exc:
                    readiness = classify_provider_exception(
                        exc,
                        provider=DEFAULT_MARKET_EVIDENCE_POLICY.execution_provider,
                        observed_at=observed_at,
                    )
            if readiness is None:
                from .market_evidence import ProviderReadiness

                readiness = ProviderReadiness(
                    provider=DEFAULT_MARKET_EVIDENCE_POLICY.execution_provider,
                    state="READY" if not missing_execution else "QUOTE_MISSING",
                    ready=not missing_execution,
                    observed_at=observed_at,
                    detail=None,
                )
            gap = ExecutionInputGap(
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
                provider=DEFAULT_MARKET_EVIDENCE_POLICY.execution_provider,
                readiness=readiness,
                reason_code=(
                    "AI_SHADOW_EXECUTION_INPUT_GAP"
                    if missing_execution
                    else "AI_SHADOW_BAR_COVERAGE_GAP"
                ),
                observed_at=observed_at,
            )
            persisted = await self._append(
                repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="ai_shadow_input_gap",
                state="unavailable",
                reason_code=gap.reason_code,
                observed_at=observed_at,
                payload={
                    "policy": policy,
                    "gap": gap.model_dump(mode="json"),
                    "bar_coverage": coverage.model_dump(mode="json"),
                    "research_only": True,
                    "execution_authority": False,
                },
                identity=(policy, observed_at.astimezone(timezone.utc).isoformat(), gap.reason_code),
            )
            if persisted:
                self.data_gap_count += 1
            ai_monitor.trade_log(
                "auto_trading",
                "ai_shadow_input_gap",
                strategy_id=config.strategy_id,
                policy=policy,
                instrument_id=candidate.instrument_id,
                reason_code=gap.reason_code,
                provider_readiness=readiness.model_dump(mode="json"),
                bar_coverage=coverage.model_dump(mode="json"),
                execution_authority=False,
            )

        if not valid_rows:
            return
        return await original_ai_run_policy(
            self,
            policy=policy,
            rows=valid_rows,
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )

    ai_monitor.TradingAIShadowMonitor._run_policy = hardened_ai_run_policy

    # Count typed input gaps in existing summary/comparison calculations without
    # rewriting their mature aggregation logic.
    original_session_summary = ai_monitor.TradingAIShadowMonitor._session_summary
    original_comparison_summary = ai_monitor.TradingAIShadowMonitor._comparison_summary

    def with_gap_aliases(events):
        output = list(events)
        for event in events:
            if event.event_type == "ai_shadow_input_gap":
                output.append(event.model_copy(update={"event_type": "ai_shadow_data_gap"}))
        return output

    async def hardened_session_summary(self, *, config, repository, events, session_date, now):
        return await original_session_summary(
            self,
            config=config,
            repository=repository,
            events=with_gap_aliases(events),
            session_date=session_date,
            now=now,
        )

    async def hardened_comparison_summary(self, *, config, repository, events, session_date, cohort_candidate_count, now):
        return await original_comparison_summary(
            self,
            config=config,
            repository=repository,
            events=with_gap_aliases(events),
            session_date=session_date,
            cohort_candidate_count=cohort_candidate_count,
            now=now,
        )

    ai_monitor.TradingAIShadowMonitor._session_summary = hardened_session_summary
    ai_monitor.TradingAIShadowMonitor._comparison_summary = hardened_comparison_summary

    original_deep_run_config = strategy_deep_recovery_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config

    async def hardened_deep_run_config(self, repository, market_service, config, *, now):
        proxy = _CoverageMarketService(
            market_service,
            session_date=now.astimezone(_ET).date(),
            observed_at=now,
        )
        return await original_deep_run_config(
            self,
            repository,
            proxy,
            config,
            now=now,
        )

    strategy_deep_recovery_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config = hardened_deep_run_config

    _INSTALLED = True


__all__ = ["install_trading_data_hardening"]
