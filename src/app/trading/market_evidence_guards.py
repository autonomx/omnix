from __future__ import annotations

"""Shared market-evidence guards used by trading runtime owners."""

import hashlib
from datetime import datetime, timedelta, timezone

from .gapper_dataset import GapperCandidate
from .market_evidence import (
    DEFAULT_MARKET_EVIDENCE_POLICY,
    MARKET_EVIDENCE_POLICY_VERSION,
    classify_provider_exception,
    premarket_evidence_feature_compatible,
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
from app.trading.us_equity_calendar import EASTERN as _ET


def _morning_evidence(candidate, config):
    """Keep lightweight test doubles outside the production evidence contract."""

    if not isinstance(candidate, GapperCandidate):
        return True, ()
    return candidate_morning_evidence_eligible(candidate, config)
def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


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
            morning_eligible, morning_reasons = _morning_evidence(
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
                and premarket_evidence_feature_compatible(
                    getattr(candidate, "premarket_liquidity", None)
                )
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
            market_evidence_policy_version=(
                str(getattr(candidate, "market_evidence_policy_version", None))
                if candidate is not None
                and getattr(candidate, "market_evidence_policy_version", None)
                else MARKET_EVIDENCE_POLICY_VERSION
            ),
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
        )
        if interval == "1m" and self._observed_at.astimezone(_ET).time() >= datetime.strptime("09:30", "%H:%M").time():
            values = list(response.bars)
            assessment = assess_bar_coverage(
                values,
                session_date=self._session_date,
                observed_at=self._observed_at,
                provider="configured_history",
            )
            finalized = [bar for bar in values if getattr(bar, "is_final", False)]
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
                    assessment = assess_bar_coverage(
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
