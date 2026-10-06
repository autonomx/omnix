"""One strategy configuration's monitor pass (moved out of the class)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.apps.trading.us_equity_calendar import EASTERN as _ET

from .order_gateway import strategy_paper_access
from .paper import PaperOrderRequest
from .paper_repository import TradingPaperRepository
from .service import TradingMarketDataService
from .strategy_data_integrity import assess_universe_integrity

# The monitor imports this module lazily, so importing it here makes no cycle.
from .strategy_monitor import (
    TradingStrategyMonitor,
    _execution_audit_payload,
    _key,
    _trade_attempt_id,
    _v2_qualification_events,
)
from .strategy_repository import (
    StrategyProtection,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
)
from .strategy_risk import size_strategy_entry
from .strategy_shadow_execution import observe_shadow_execution
from .strategy_shadow_universe import (
    resolve_v2_runtime_archive,
)
from .strategy_v2_qualification import (
    evaluate_v2_prospective_qualification,
    v2_profile_fingerprint,
)
from .trade_logging import trade_log


async def run_config(
    monitor: TradingStrategyMonitor,
    config: TradingStrategyConfigDocument,
    strategy_repository: TradingStrategyRepository,
    paper_repository: TradingPaperRepository,
    market_service: TradingMarketDataService,
) -> None:
    paper_repository = strategy_paper_access(
        paper_repository,
        monitor=monitor,
        config=config,
        strategy_repository=strategy_repository,
        market_service=market_service,
    )
    cycle_started_at = datetime.now(timezone.utc)
    log_cycle_heartbeat = monitor._should_log_diagnostic(
        ("strategy_cycle_heartbeat", config.strategy_id),
        cycle_started_at,
    )
    if log_cycle_heartbeat:
        trade_log(
            "auto_trading",
            "strategy_cycle_start",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            account_id=config.account_id,
            strategy_kind=config.strategy_kind,
            strategy_version=config.strategy_version,
            mode=config.mode,
            enabled=config.enabled,
            active_universe_id=config.active_universe_id,
            config=config.config,
            risk_profile=config.risk,
        )
    await monitor._reconcile_protections(
        config,
        strategy_repository,
        paper_repository,
        market_service,
    )
    if config.mode == "off" or not config.enabled:
        if log_cycle_heartbeat:
            trade_log(
                "auto_trading",
                "strategy_cycle_skipped",
                run_id=monitor.current_run_id,
                strategy_id=config.strategy_id,
                reason="mode_off" if config.mode == "off" else "disabled",
            )
        return

    now_utc = datetime.now(timezone.utc)
    if config.strategy_kind == "stoch_rsi_5m_v1":
        await monitor._run_stoch_rsi_5m_config(
            config,
            strategy_repository,
            market_service,
            now_utc=now_utc,
        )
        return

    if config.mode == "auto_paper" and config.config.strategy_version == "2.0.0":
        qualification_events = await asyncio.to_thread(
            _v2_qualification_events,
            strategy_repository,
            config.strategy_id,
            now=now_utc,
        )
        qualification = await asyncio.to_thread(
            evaluate_v2_prospective_qualification,
            config,
            qualification_events,
        )
        if not qualification.auto_paper_authorized:
            monitor._set_auto_paper_readiness(
                config,
                state="blocked",
                reason="qualification_not_authorized",
                observed_at=now_utc,
            )
            if log_cycle_heartbeat:
                trade_log(
                    "auto_trading",
                    "v2_auto_paper_qualification_blocked",
                    run_id=monitor.current_run_id,
                    strategy_id=config.strategy_id,
                    profile_fingerprint=qualification.current_profile_fingerprint,
                    evidence_fingerprint=qualification.evidence_fingerprint,
                    reason_codes=qualification.reason_codes,
                    matched_eligible_trade_count=qualification.matched_eligible_trade_count,
                    execution_match_rate=qualification.execution_match_rate,
                    expectancy_r=qualification.expectancy_r,
                    one_sided_90_lcb_r=qualification.one_sided_90_lcb_r,
                    max_drawdown_r=qualification.max_drawdown_r,
                    execution_authority=False,
                )
            return
    now_et = now_utc.astimezone(_ET)
    today_et = now_et.date()
    day_start_et = datetime(today_et.year, today_et.month, today_et.day, tzinfo=_ET)
    day_end_et = day_start_et + timedelta(days=1)

    universe_source = "active_universe"
    if config.active_universe_id is not None:
        universe = await asyncio.to_thread(
            strategy_repository.get_universe,
            config.active_universe_id,
        )
    else:
        universe = await asyncio.to_thread(
            resolve_v2_runtime_archive,
            config,
            strategy_repository,
            now=now_utc,
        )
        universe_source = (
            "auto_archive_auto_paper"
            if config.mode == "auto_paper"
            else "auto_archive_shadow"
        )
        if universe is None:
            if config.mode == "auto_paper":
                monitor._set_auto_paper_readiness(
                    config,
                    state="blocked",
                    reason="daily_universe_not_ready",
                    observed_at=now_utc,
                )
            if log_cycle_heartbeat:
                reason = (
                    "v2_auto_paper_archive_not_ready"
                    if config.mode == "auto_paper"
                    and config.config.strategy_version == "2.0.0"
                    else (
                        "v2_shadow_archive_not_ready"
                        if config.mode == "shadow"
                        and config.config.strategy_version == "2.0.0"
                        else "no_active_universe"
                    )
                )
                trade_log(
                    "auto_trading",
                    "strategy_cycle_skipped",
                    run_id=monitor.current_run_id,
                    strategy_id=config.strategy_id,
                    reason=reason,
                    execution_authority=False,
                )
            return

    integrity = assess_universe_integrity(universe)
    if log_cycle_heartbeat:
        trade_log(
            "auto_trading",
            "universe_loaded",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            universe_id=universe.universe_id,
            runtime_universe_source=universe_source,
            session_date=universe.session_date,
            evaluation_time=universe.evaluation_time,
            discovery_source=universe.discovery_source,
            source_fingerprint=universe.source_fingerprint,
            candidate_count=len(universe.candidates),
            capture_on_time=integrity.capture_on_time,
            cohort_complete=integrity.cohort_complete,
            cohort_integrity=integrity.cohort_integrity,
            market_data_complete=integrity.market_data_complete,
            prospective_eligible=integrity.prospective_eligible,
            integrity_reason_codes=integrity.reason_codes,
        )
    if universe.session_date != today_et:
        monitor._set_auto_paper_readiness(
            config,
            state="blocked",
            reason="universe_session_mismatch",
            observed_at=now_utc,
            universe_id=universe.universe_id,
        )
        rejection_time = day_start_et.astimezone(timezone.utc)
        for candidate in universe.candidates:
            monitor.rejection_count += 1
            await monitor._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="rejection",
                state="rejected",
                reason_code="UNIVERSE_SESSION_MISMATCH",
                observed_at=rejection_time,
                payload={
                    "universe_id": universe.universe_id,
                    "universe_session_date": universe.session_date.isoformat(),
                    "runtime_session_date": today_et.isoformat(),
                },
            )
        return

    if universe.discovery_source == "finviz" and not integrity.prospective_eligible:
        monitor._set_auto_paper_readiness(
            config,
            state="blocked",
            reason=(
                integrity.reason_codes[0]
                if integrity.reason_codes
                else "universe_data_integrity_invalid"
            ),
            observed_at=now_utc,
            universe_id=universe.universe_id,
        )
        await monitor._event(
            strategy_repository,
            config,
            instrument_id="__universe__",
            event_type="universe_integrity",
            state="invalid",
            reason_code=(
                integrity.reason_codes[0]
                if integrity.reason_codes
                else "UNIVERSE_DATA_INTEGRITY_INVALID"
            ),
            observed_at=universe.evaluation_time,
            payload={
                "universe_id": universe.universe_id,
                **integrity.model_dump(mode="json"),
                "research_only": True,
                "execution_authority": False,
            },
        )
        return

    monitor._set_auto_paper_readiness(
        config,
        state="ready",
        reason="qualified_daily_universe_ready",
        observed_at=now_utc,
        universe_id=universe.universe_id,
    )

    proposals = await monitor._evaluate_candidates(
        config,
        strategy_repository,
        market_service,
        universe,
    )
    if config.mode == "shadow" and proposals:
        for proposal in proposals:
            candidate = proposal.candidate
            result = proposal.result
            assert result.signal is not None
            try:
                evidence = await asyncio.to_thread(
                    observe_shadow_execution,
                    market_service,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                )
            except Exception as exc:
                payload = {
                    "strategy_version": config.config.strategy_version,
                    "mode": "shadow",
                    "universe_id": universe.universe_id,
                    "universe_source": universe_source,
                    "profile_fingerprint": (
                        v2_profile_fingerprint(config.config)
                        if config.config.strategy_version == "2.0.0"
                        else None
                    ),
                    "signal": result.signal.model_dump(mode="json"),
                    "features": result.features.model_dump(mode="json"),
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                    "execution_authority": False,
                }
                await monitor._event(
                    strategy_repository,
                    config,
                    instrument_id=candidate.instrument_id,
                    event_type="shadow_execution",
                    state=result.state,
                    reason_code="SHADOW_EXECUTION_UNAVAILABLE",
                    observed_at=proposal.observed_at,
                    payload=payload,
                )
                trade_log(
                    "auto_trading",
                    "shadow_execution_unavailable",
                    run_id=monitor.current_run_id,
                    strategy_id=config.strategy_id,
                    instrument_id=candidate.instrument_id,
                    **payload,
                )
                continue

            payload = {
                "strategy_version": config.config.strategy_version,
                "mode": "shadow",
                "universe_id": universe.universe_id,
                "universe_source": universe_source,
                "profile_fingerprint": (
                    v2_profile_fingerprint(config.config)
                    if config.config.strategy_version == "2.0.0"
                    else None
                ),
                "signal": result.signal.model_dump(mode="json"),
                "features": result.features.model_dump(mode="json"),
                "execution": evidence.execution,
                "execution_authority": False,
            }
            await monitor._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="shadow_execution",
                state=result.state,
                reason_code=evidence.reason_code,
                observed_at=proposal.observed_at,
                payload=payload,
            )
            trade_log(
                "auto_trading",
                "shadow_execution_observation",
                run_id=monitor.current_run_id,
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                reason_code=evidence.reason_code,
                **payload,
            )

        trade_log(
            "auto_trading",
            "strategy_cycle_no_entry_work",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            mode=config.mode,
            proposal_count=len(proposals),
            shadow_execution_observed=True,
        )
        return

    if config.mode != "auto_paper" or not proposals:
        trade_log(
            "auto_trading",
            "strategy_cycle_no_entry_work",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            mode=config.mode,
            proposal_count=len(proposals),
        )
        return

    snapshot = await asyncio.to_thread(paper_repository.snapshot, config.account_id)
    if hasattr(strategy_repository, "entry_events_between"):
        entry_events = await asyncio.to_thread(
            strategy_repository.entry_events_between,
            config.strategy_id,
            start_time=day_start_et,
            end_time=day_end_et,
        )
    else:
        recent_events = await asyncio.to_thread(
            strategy_repository.recent_events,
            config.strategy_id,
            500,
        )
        entry_events = [
            event
            for event in recent_events
            if event.event_type == "entry_order_submitted"
            and event.observed_at.astimezone(_ET).date() == today_et
        ]
    trades_today = len(entry_events)
    traded_symbols = {event.instrument_id for event in entry_events}
    submitted_attempts = {
        str(event.payload.get("trade_attempt_id"))
        if event.payload.get("trade_attempt_id")
        else _trade_attempt_id(config.strategy_id, event.instrument_id, event.observed_at)
        for event in entry_events
    }

    daily_realized_pnl: Decimal | None = None
    if hasattr(strategy_repository, "daily_paper_pnl"):
        daily_realized_pnl = await asyncio.to_thread(
            strategy_repository.daily_paper_pnl,
            config.account_id,
            start_time=day_start_et,
            end_time=day_end_et,
        )

    protections = await asyncio.to_thread(
        strategy_repository.list_protections,
        config.strategy_id,
        active_only=True,
    )
    protected_symbols = {item.instrument_id for item in protections}
    positions_by_instrument = {position.instrument_id: position for position in snapshot.positions}
    open_risk = Decimal("0")
    for item in protections:
        if item.status not in {"pending_entry", "active"}:
            continue
        position = positions_by_instrument.get(item.instrument_id)
        if (
            config.config.strategy_version == "2.0.0"
            and item.status == "active"
            and position is not None
        ):
            # After V2 profit protection moves above entry, remaining downside
            # risk is zero rather than the old target/stop geometric estimate.
            per_share_risk = max(Decimal("0"), position.average_cost - item.stop_price)
        else:
            per_share_risk = max(
                Decimal("0"),
                (item.target_price - item.stop_price)
                / (config.config.reward_multiple + Decimal("1")),
            )
        open_risk += item.quantity * per_share_risk
    trade_log(
        "auto_trading",
        "portfolio_risk_context",
        run_id=monitor.current_run_id,
        strategy_id=config.strategy_id,
        account_id=config.account_id,
        trades_today=trades_today,
        traded_symbols=sorted(traded_symbols),
        submitted_attempts=sorted(submitted_attempts),
        protected_symbols=sorted(protected_symbols),
        daily_realized_pnl=daily_realized_pnl,
        open_strategy_risk=open_risk,
        balances=[balance.model_dump(mode="json") for balance in snapshot.balances],
        positions=[position.model_dump(mode="json") for position in snapshot.positions],
        open_orders=[order.model_dump(mode="json") for order in snapshot.open_orders],
    )

    for proposal in proposals:
        candidate = proposal.candidate
        result = proposal.result
        assert result.signal is not None
        observed_at = proposal.observed_at
        trade_attempt_id = _trade_attempt_id(
            config.strategy_id,
            candidate.instrument_id,
            observed_at,
        )
        if trade_attempt_id in submitted_attempts:
            trade_log(
                "auto_trading",
                "candidate_skipped",
                run_id=monitor.current_run_id,
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                trade_attempt_id=trade_attempt_id,
                reason="trade_attempt_already_submitted",
            )
            continue
        if candidate.instrument_id in protected_symbols:
            trade_log(
                "auto_trading",
                "candidate_skipped",
                run_id=monitor.current_run_id,
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                reason="existing_strategy_protection",
            )
            continue
        try:
            execution = await asyncio.to_thread(
                market_service.execution_observation,
                candidate.instrument_id,
                candidate.binding_id,
            )
        except Exception as exc:
            monitor.rejection_count += 1
            await monitor._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="rejection",
                state=result.state,
                reason_code="DATA_UNAVAILABLE",
                observed_at=observed_at,
                payload={"detail": str(exc), "trade_attempt_id": trade_attempt_id},
            )
            trade_log(
                "auto_trading",
                "execution_observation_error",
                run_id=monitor.current_run_id,
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                trade_attempt_id=trade_attempt_id,
                error_type=type(exc).__name__,
                detail=str(exc),
            )
            continue
        execution_payload = _execution_audit_payload(execution)
        trade_log(
            "auto_trading",
            "execution_observation",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            instrument_id=candidate.instrument_id,
            trade_attempt_id=trade_attempt_id,
            signal=result.signal,
            execution=execution_payload,
        )
        if not execution.execution_eligible:
            monitor.rejection_count += 1
            await monitor._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="rejection",
                state=result.state,
                reason_code="DATA_STALE_OR_INELIGIBLE",
                observed_at=observed_at,
                payload={
                    "trade_attempt_id": trade_attempt_id,
                    "reasons": list(execution.rejection_reasons),
                    "execution": execution_payload,
                },
            )
            continue
        decision = size_strategy_entry(
            snapshot,
            result.signal,
            config.risk,
            spread_bps=execution.spread_bps,
            trades_today=trades_today,
            traded_symbols_today=traded_symbols,
            reserved_instruments=protected_symbols,
            daily_realized_pnl=daily_realized_pnl,
            open_strategy_risk=open_risk,
            observed_at=now_utc,
        )
        decision_payload = decision.model_dump(mode="json")
        profile_fingerprint = (
            v2_profile_fingerprint(config.config)
            if config.config.strategy_version == "2.0.0"
            else config.config.strategy_version
        )
        risk_event_payload = {
            "trade_attempt_id": trade_attempt_id,
            "strategy_version": config.config.strategy_version,
            "profile_fingerprint": profile_fingerprint,
            "universe_id": universe.universe_id,
            "risk_decision": decision_payload,
            "execution": execution_payload,
            "signal": result.signal.model_dump(mode="json"),
            "features": result.features.model_dump(mode="json"),
            "trades_today_before_entry": trades_today,
            "daily_realized_pnl": (
                str(daily_realized_pnl) if daily_realized_pnl is not None else None
            ),
            "open_strategy_risk_before_entry": str(open_risk),
        }
        await monitor._event(
            strategy_repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="risk_decision",
            state="approved" if decision.allowed else "rejected",
            reason_code=decision.reason_code,
            observed_at=observed_at,
            payload=risk_event_payload,
        )
        trade_log(
            "auto_trading",
            "risk_decision",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            account_id=config.account_id,
            instrument_id=candidate.instrument_id,
            trade_attempt_id=trade_attempt_id,
            observed_at=observed_at,
            trades_today=trades_today,
            daily_realized_pnl=daily_realized_pnl,
            open_strategy_risk=open_risk,
            spread_bps=execution.spread_bps,
            signal=result.signal,
            decision=decision_payload,
        )
        if not decision.allowed:
            monitor.rejection_count += 1
            await monitor._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="rejection",
                state=result.state,
                reason_code=decision.reason_code,
                observed_at=observed_at,
                payload={
                    **decision_payload,
                    "trade_attempt_id": trade_attempt_id,
                    "execution": execution_payload,
                    "signal": result.signal.model_dump(mode="json"),
                },
            )
            continue

        order_key = _key(config.strategy_id, trade_attempt_id, "entry")
        order_id = f"strat-{order_key[:32]}"
        protection = StrategyProtection(
            strategy_id=config.strategy_id,
            protection_id=f"prot-{order_key[:32]}",
            account_id=config.account_id,
            instrument_id=candidate.instrument_id,
            entry_order_id=order_id,
            stop_price=result.signal.stop_price,
            target_price=result.signal.target_price,
            initial_stop_price=result.signal.stop_price,
            initial_target_price=(
                None if config.config.strategy_version == "2.0.0"
                else result.signal.target_price
            ),
            quantity=decision.quantity,
            status="pending_entry",
        )
        # Arm protection before the order can become executable. The strategy
        # protection table intentionally does not require the paper order FK,
        # so a crash between these writes is fail-closed rather than exposed.
        await asyncio.to_thread(strategy_repository.save_protection, protection)
        try:
            await asyncio.to_thread(
                paper_repository.place_entry,
                config.account_id,
                PaperOrderRequest(
                    order_id=order_id,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                    side="buy",
                    order_type="market",
                    quantity=decision.quantity,
                    reference_price=execution.ask or execution.last,
                    idempotency_key=order_key,
                ),
                trade_attempt_id=trade_attempt_id,
            )
        except ValueError as exc:
            protection.status = "cancelled"
            protection.trigger_reason = "entry_submit_failed"
            try:
                await asyncio.to_thread(strategy_repository.save_protection, protection)
            except ValueError as cleanup_exc:
                monitor.last_error = f"entry_protection_cleanup: {cleanup_exc}"
            monitor.rejection_count += 1
            await monitor._event(
                strategy_repository,
                config,
                instrument_id=candidate.instrument_id,
                event_type="rejection",
                state=result.state,
                reason_code="PAPER_ORDER_REJECTED",
                observed_at=observed_at,
                payload={
                    "detail": str(exc),
                    "trade_attempt_id": trade_attempt_id,
                    "order_id": order_id,
                    "execution": execution_payload,
                    "risk_decision": decision_payload,
                    "signal": result.signal.model_dump(mode="json"),
                },
            )
            trade_log(
                "auto_trading",
                "entry_order_rejected",
                run_id=monitor.current_run_id,
                strategy_id=config.strategy_id,
                account_id=config.account_id,
                instrument_id=candidate.instrument_id,
                trade_attempt_id=trade_attempt_id,
                order_id=order_id,
                detail=str(exc),
                execution=execution_payload,
                risk_decision=decision_payload,
            )
            continue

        await monitor._event(
            strategy_repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="entry_order_submitted",
            state="entry_ready",
            reason_code="AUTO_PAPER_ENTRY_SUBMITTED",
            observed_at=observed_at,
            payload={
                "trade_attempt_id": trade_attempt_id,
                "strategy_version": config.config.strategy_version,
                "profile_fingerprint": profile_fingerprint,
                "order_id": order_id,
                "quantity": str(decision.quantity),
                "reference_price": str(execution.ask or execution.last),
                "stop_price": str(result.signal.stop_price),
                "target_price": str(result.signal.target_price),
                "quality_score": result.signal.quality_score,
                "structure_interval": config.config.structure_interval,
                "execution_interval": config.config.execution_interval,
                "priority": [
                    observed_at.astimezone(timezone.utc).isoformat(),
                    -result.signal.quality_score,
                    candidate.discovery_rank if candidate.discovery_rank is not None else 10**9,
                    candidate.instrument_id,
                ],
                "signal": result.signal.model_dump(mode="json"),
                "features": result.features.model_dump(mode="json"),
                "execution": execution_payload,
                "risk_decision": decision_payload,
                "trades_today_before_entry": trades_today,
                "daily_realized_pnl": str(daily_realized_pnl) if daily_realized_pnl is not None else None,
                "open_strategy_risk_before_entry": str(open_risk),
                "universe_id": universe.universe_id,
            },
        )
        trade_log(
            "auto_trading",
            "entry_order_submitted",
            run_id=monitor.current_run_id,
            strategy_id=config.strategy_id,
            account_id=config.account_id,
            instrument_id=candidate.instrument_id,
            trade_attempt_id=trade_attempt_id,
            order_id=order_id,
            quantity=decision.quantity,
            reference_price=execution.ask or execution.last,
            signal=result.signal,
            features=result.features,
            execution=execution_payload,
            risk_decision=decision_payload,
        )
        monitor.paper_order_count += 1
        trades_today += 1
        traded_symbols.add(candidate.instrument_id)
        submitted_attempts.add(trade_attempt_id)
        protected_symbols.add(candidate.instrument_id)
        open_risk += decision.estimated_risk
