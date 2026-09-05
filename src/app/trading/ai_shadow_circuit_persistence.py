from __future__ import annotations

"""Durable provider-circuit state for AI-shadow research.

The circuit is operational state only: it never grants execution authority and
never blocks deterministic strategy evaluation. Persistence is best-effort so a
repository outage cannot become a trading outage.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

from . import ai_shadow_reliability as reliability
from .strategy_managed_finviz_shadow import MANAGED_FINVIZ_SHADOW_STRATEGY_ID
from .strategy_repository import StrategyEvent, default_strategy_repository


_EVENT_TYPE = "ai_shadow_provider_health"
_RUN_ID = "ai-shadow-provider-health"
_INSTALLED = False


def _enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return False
    return os.environ.get(
        "OMNIX_TRADING_AI_SHADOW_CIRCUIT_PERSISTENCE",
        "1",
    ).strip().casefold() in {"1", "true", "yes", "on"}


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _persist(*, state: str, failure_count: int, delay_seconds: int = 0) -> None:
    if not _enabled():
        return
    observed_at = datetime.now(timezone.utc)
    open_until = (
        observed_at + timedelta(seconds=delay_seconds)
        if state == "open" and delay_seconds > 0
        else None
    )
    identity = (
        f"{MANAGED_FINVIZ_SHADOW_STRATEGY_ID}|{_EVENT_TYPE}|{state}|"
        f"{failure_count}|{observed_at.isoformat()}"
    )
    idem = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    event = StrategyEvent(
        strategy_id=MANAGED_FINVIZ_SHADOW_STRATEGY_ID,
        event_id=idem[:32],
        run_id=_RUN_ID,
        instrument_id="__provider__",
        event_type=_EVENT_TYPE,
        state=state,
        reason_code=(
            "AI_SHADOW_PROVIDER_CIRCUIT_OPEN"
            if state == "open"
            else "AI_SHADOW_PROVIDER_CIRCUIT_RECOVERED"
        ),
        observed_at=observed_at,
        idempotency_key=idem,
        payload={
            "failure_count": failure_count,
            "backoff_seconds": delay_seconds,
            "open_until_utc": open_until.isoformat() if open_until else None,
            "research_only": True,
            "execution_authority": False,
        },
    )
    try:
        default_strategy_repository().append_event(event)
    except Exception:
        # Provider health persistence is diagnostic/recovery state. It must never
        # interfere with deterministic trading or turn a DB issue into retries.
        return


class PersistentCircuitState(reliability._CircuitState):
    def __init__(self) -> None:
        super().__init__()
        self._hydrated = False

    def _hydrate(self, now_monotonic: float) -> None:
        if self._hydrated or not _enabled():
            self._hydrated = True
            return
        try:
            events = default_strategy_repository().recent_events(
                MANAGED_FINVIZ_SHADOW_STRATEGY_ID,
                500,
            )
        except Exception:
            return
        health = [event for event in events if event.event_type == _EVENT_TYPE]
        if health:
            latest = max(health, key=lambda event: (event.observed_at, event.event_id))
            payload = latest.payload if isinstance(latest.payload, dict) else {}
            if latest.state == "open":
                self.failure_count = max(0, int(payload.get("failure_count") or 0))
                open_until = _parse_datetime(payload.get("open_until_utc"))
                if open_until is not None:
                    remaining = max(
                        0.0,
                        (open_until - datetime.now(timezone.utc)).total_seconds(),
                    )
                    self.open_until_monotonic = now_monotonic + remaining
            else:
                self.failure_count = 0
                self.open_until_monotonic = 0.0
        self._hydrated = True

    def is_open(self, now: float) -> bool:
        self._hydrate(now)
        return super().is_open(now)

    def retry_after(self, now: float) -> int:
        self._hydrate(now)
        return super().retry_after(now)

    def trip(self, now: float) -> int:
        self._hydrate(now)
        delay = super().trip(now)
        _persist(
            state="open",
            failure_count=self.failure_count,
            delay_seconds=delay,
        )
        return delay

    def success(self) -> None:
        had_failure = self.failure_count > 0 or self.open_until_monotonic > 0
        super().success()
        if had_failure:
            _persist(state="closed", failure_count=0)

    def reset_for_tests(self) -> None:
        super().success()
        self._hydrated = True


def install_persistent_ai_shadow_circuit() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    reliability._CIRCUIT = PersistentCircuitState()
    _INSTALLED = True


__all__ = ["PersistentCircuitState", "install_persistent_ai_shadow_circuit"]
