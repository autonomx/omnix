from __future__ import annotations

"""Durable zero-authority IBKR observation and recovery diagnostics.

Session diagnostics live in PostgreSQL (WP-8.3). Quote callbacks queue their
updates; the queue is applied in one transaction every 50 events or 2 seconds,
and before any read, so the market-data thread does not write per tick.
"""

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from .evidence_storage import IbkrSessionEvidence, default_ibkr_session_evidence

logger = logging.getLogger(__name__)


class IbkrEvidenceStore:
    """Session-scoped diagnostics used to decide whether IBKR may be promoted."""

    def __init__(
        self,
        backend: IbkrSessionEvidence | None = None,
        *,
        flush_events: int = 50,
        flush_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backend = backend if backend is not None else default_ibkr_session_evidence()
        self.flush_events = max(1, int(flush_events))
        self.flush_seconds = max(0.0, float(flush_seconds))
        self._clock = clock
        self._lock = threading.RLock()
        self._pending: dict[date, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)
        self._pending_count = 0
        self._last_flush = clock()

    @staticmethod
    def _empty(session_date: date) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": "ibkr",
            "session_date": session_date.isoformat(),
            "quote_event_count": 0,
            "live_quote_event_count": 0,
            "nonlive_quote_event_count": 0,
            "entitlement_failure_count": 0,
            "missing_quote_count": 0,
            "subscription_error_count": 0,
            "quote_age_sample_count": 0,
            "quote_age_seconds_sum": "0",
            "quote_age_seconds_max": "0",
            "spread_bps_sample_count": 0,
            "spread_bps_sum": "0",
            "iex_comparison_count": 0,
            "last_price_diff_bps_sum": "0",
            "last_price_diff_bps_max_abs": "0",
            "spread_comparison_count": 0,
            "spread_diff_bps_sum": "0",
            "recovery_attempt_count": 0,
            "shadow_recoverable_bar_count": 0,
            "applied_recovery_bar_count": 0,
            "evaluability_improvement_count": 0,
            "gateway_disconnect_observation_count": 0,
            "max_reconnect_count": 0,
            "max_active_subscriptions": 0,
            "reason_counts": {},
        }

    def _read(self, session_date: date) -> dict[str, Any]:
        self.flush()
        payload = self._empty(session_date)
        stored = self.backend.read(session_date)
        if stored:
            payload.update(stored)
        return payload

    def _mutate(self, session_date: date, mutator: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._pending[session_date].append(mutator)
            self._pending_count += 1
            due = (
                self._pending_count >= self.flush_events
                or self._clock() - self._last_flush >= self.flush_seconds
            )
        if due:
            self.flush()

    def flush(self) -> None:
        """Apply every queued update; a failed write is logged and dropped."""
        with self._lock:
            pending, self._pending = self._pending, defaultdict(list)
            self._pending_count = 0
            self._last_flush = self._clock()
        for session_date, mutators in pending.items():
            try:
                self.backend.apply(session_date, self._empty(session_date), mutators)
            except Exception:
                logger.warning("IBKR evidence for %s not recorded", session_date, exc_info=True)

    @staticmethod
    def _decimal(payload: dict[str, Any], key: str) -> Decimal:
        try:
            return Decimal(str(payload.get(key, "0") or "0"))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _increment_reason(payload: dict[str, Any], reason: str) -> None:
        reasons = dict(payload.get("reason_counts") or {})
        reasons[reason] = int(reasons.get(reason, 0) or 0) + 1
        payload["reason_counts"] = dict(sorted(reasons.items()))

    def record_quote(
        self,
        session_date: date,
        *,
        market_data_type: str,
        live_entitled: bool | None,
        quote_age_seconds: Decimal | None,
        spread_bps: Decimal | None,
        last_price_diff_bps: Decimal | None = None,
        spread_diff_bps: Decimal | None = None,
    ) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["quote_event_count"] = int(payload["quote_event_count"]) + 1
            if market_data_type == "LIVE" and live_entitled is True:
                payload["live_quote_event_count"] = int(payload["live_quote_event_count"]) + 1
            else:
                payload["nonlive_quote_event_count"] = int(payload["nonlive_quote_event_count"]) + 1
                if live_entitled is False or market_data_type in {"DELAYED", "DELAYED_FROZEN", "FROZEN"}:
                    payload["entitlement_failure_count"] = int(payload["entitlement_failure_count"]) + 1
            if quote_age_seconds is not None:
                payload["quote_age_sample_count"] = int(payload["quote_age_sample_count"]) + 1
                total = self._decimal(payload, "quote_age_seconds_sum") + quote_age_seconds
                maximum = max(self._decimal(payload, "quote_age_seconds_max"), quote_age_seconds)
                payload["quote_age_seconds_sum"] = str(total)
                payload["quote_age_seconds_max"] = str(maximum)
            if spread_bps is not None:
                payload["spread_bps_sample_count"] = int(payload["spread_bps_sample_count"]) + 1
                payload["spread_bps_sum"] = str(
                    self._decimal(payload, "spread_bps_sum") + spread_bps
                )
            if last_price_diff_bps is not None:
                payload["iex_comparison_count"] = int(payload["iex_comparison_count"]) + 1
                payload["last_price_diff_bps_sum"] = str(
                    self._decimal(payload, "last_price_diff_bps_sum") + last_price_diff_bps
                )
                payload["last_price_diff_bps_max_abs"] = str(
                    max(
                        self._decimal(payload, "last_price_diff_bps_max_abs"),
                        abs(last_price_diff_bps),
                    )
                )
                if spread_diff_bps is not None:
                    payload["spread_comparison_count"] = (
                        int(payload["spread_comparison_count"]) + 1
                    )
                    payload["spread_diff_bps_sum"] = str(
                        self._decimal(payload, "spread_diff_bps_sum") + spread_diff_bps
                    )

        self._mutate(session_date, mutate)

    def record_missing_quote(self, session_date: date, reason: str) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["missing_quote_count"] = int(payload["missing_quote_count"]) + 1
            self._increment_reason(payload, reason)

        self._mutate(session_date, mutate)

    def record_subscription_error(self, session_date: date, reason: str) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["subscription_error_count"] = int(payload["subscription_error_count"]) + 1
            self._increment_reason(payload, reason)

        self._mutate(session_date, mutate)

    def record_recovery(
        self,
        session_date: date,
        *,
        attempted: bool,
        recoverable_count: int,
        applied_count: int,
        before_unresolved_count: int,
        after_unresolved_count: int,
    ) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            if attempted:
                payload["recovery_attempt_count"] = int(payload["recovery_attempt_count"]) + 1
            payload["shadow_recoverable_bar_count"] = (
                int(payload["shadow_recoverable_bar_count"]) + max(0, int(recoverable_count))
            )
            payload["applied_recovery_bar_count"] = (
                int(payload["applied_recovery_bar_count"]) + max(0, int(applied_count))
            )
            if after_unresolved_count < before_unresolved_count:
                payload["evaluability_improvement_count"] = (
                    int(payload["evaluability_improvement_count"]) + 1
                )

        self._mutate(session_date, mutate)

    def record_runtime(
        self,
        session_date: date,
        *,
        connected: bool,
        reconnect_count: int,
        active_subscriptions: int,
    ) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            if not connected:
                payload["gateway_disconnect_observation_count"] = (
                    int(payload["gateway_disconnect_observation_count"]) + 1
                )
            payload["max_reconnect_count"] = max(
                int(payload["max_reconnect_count"]),
                max(0, int(reconnect_count)),
            )
            payload["max_active_subscriptions"] = max(
                int(payload["max_active_subscriptions"]),
                max(0, int(active_subscriptions)),
            )

        self._mutate(session_date, mutate)

    def session_diagnostics(self, session_date: date) -> dict[str, Any]:
        payload = self._read(session_date)
        age_count = int(payload.get("quote_age_sample_count", 0) or 0)
        spread_count = int(payload.get("spread_bps_sample_count", 0) or 0)
        compare_count = int(payload.get("iex_comparison_count", 0) or 0)
        spread_compare_count = int(payload.get("spread_comparison_count", 0) or 0)
        payload["quote_age_seconds_mean"] = (
            str(self._decimal(payload, "quote_age_seconds_sum") / age_count)
            if age_count
            else None
        )
        payload["spread_bps_mean"] = (
            str(self._decimal(payload, "spread_bps_sum") / spread_count)
            if spread_count
            else None
        )
        payload["last_price_diff_bps_mean"] = (
            str(self._decimal(payload, "last_price_diff_bps_sum") / compare_count)
            if compare_count
            else None
        )
        payload["spread_diff_bps_mean"] = (
            str(self._decimal(payload, "spread_diff_bps_sum") / spread_compare_count)
            if spread_compare_count
            else None
        )
        return payload


_DEFAULT_STORE: IbkrEvidenceStore | None = None
_DEFAULT_LOCK = threading.Lock()


def default_ibkr_evidence_store() -> IbkrEvidenceStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_STORE is None:
                _DEFAULT_STORE = IbkrEvidenceStore()
    return _DEFAULT_STORE


__all__ = ["IbkrEvidenceStore", "default_ibkr_evidence_store"]
