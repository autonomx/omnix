from __future__ import annotations

"""Durable zero-authority IBKR observation and recovery diagnostics."""

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


def _default_root() -> Path:
    configured = os.getenv("OMNIX_TRADING_IBKR_EVIDENCE_DIR", "").strip()
    if configured:
        return Path(configured)
    if os.getenv("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return Path(tempfile.gettempdir()) / f"omnix-ibkr-evidence-test-{os.getpid()}"
    return Path("resources/trading/ibkr_evidence")


@contextmanager
def _interprocess_file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class IbkrEvidenceStore:
    """Session-scoped diagnostics used to decide whether IBKR may be promoted."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self._lock = threading.RLock()

    def _session_path(self, session_date: date) -> Path:
        return self.root / "sessions" / f"{session_date.isoformat()}.json"

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
        baseline = self._empty(session_date)
        path = self._session_path(session_date)
        if not path.exists():
            return baseline
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return baseline
        if not isinstance(payload, dict):
            return baseline
        baseline.update(payload)
        return baseline

    def _mutate(self, session_date: date, mutator) -> None:
        path = self._session_path(session_date)
        lock_path = path.with_suffix(".lock")
        with self._lock, _interprocess_file_lock(lock_path):
            payload = self._read(session_date)
            mutator(payload)
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)

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
