from __future__ import annotations

"""Durable Yahoo evidence and same-feed relative-volume authority.

Yahoo is useful free market evidence, but it is not represented as consolidated
SIP authority and never becomes execution authority.  This module persists
finalized Yahoo 1-minute observations locally so transient HTTP failures do not
erase evidence that Omnix has already observed.

The store is intentionally provider-scoped.  Yahoo-relative RVOL compares a
Yahoo numerator with Yahoo historical denominators at the same clock minute; it
must never be relabelled as consolidated US-market volume.
"""

import hashlib
import json
import os
import threading
import tempfile
from contextlib import contextmanager
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import AdjustmentMode, MarketBar


_ET = ZoneInfo("America/New_York")
_PREMARKET_OPEN = time(4, 0)
_REGULAR_OPEN = time(9, 30)
def _default_root() -> Path:
    configured = os.getenv("OMNIX_TRADING_YAHOO_EVIDENCE_DIR", "").strip()
    if configured:
        return Path(configured)
    if os.getenv("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return Path(tempfile.gettempdir()) / f"omnix-yahoo-evidence-test-{os.getpid()}"
    return Path("resources/trading/yahoo_evidence")

YahooVolumeAuthority = Literal["provider_relative"]
KnowledgeMode = Literal["live", "causal_replay", "retroactive_research"]


@contextmanager
def _interprocess_file_lock(path: Path):
    """Cross-platform advisory lock for the single Yahoo evidence file being updated."""

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


class YahooRelativeVolumeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    observed_at: datetime
    cutoff_clock: str
    current_volume: Decimal = Field(ge=0)
    current_dollar_volume: Decimal = Field(ge=0)
    baseline_mean_volume: Decimal | None = Field(default=None, ge=0)
    baseline_session_count: int = Field(ge=0)
    rejected_baseline_session_count: int = Field(default=0, ge=0)
    baseline_min_coverage_ratio: Decimal = Field(default=Decimal("0.90"), ge=0, le=1)
    relative_volume: Decimal | None = Field(default=None, ge=0)
    current_bar_count: int = Field(ge=0)
    current_nonzero_bar_count: int = Field(ge=0)
    expected_bar_count: int = Field(ge=0)
    coverage_ratio: Decimal | None = Field(default=None, ge=0)
    volume_authority: YahooVolumeAuthority = "provider_relative"
    provider: Literal["yahoo"] = "yahoo"
    feed: Literal["extended_hours"] = "extended_hours"

    @field_validator("observed_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Yahoo evidence timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


class YahooEvidenceStore:
    """Atomic, append-by-revision local store for Yahoo 1-minute evidence."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self._lock = threading.RLock()
        self._persisted_bar_count = 0
        self._loaded_bar_count = 0
        self._repair_attempt_count = 0
        self._repair_success_count = 0
        self._repaired_bar_count = 0
        self._unresolved_repair_count = 0
        self._rvol_baseline_hit_count = 0
        self._rvol_baseline_miss_count = 0
        self._causal_replay_rejection_count = 0
        self._evaluation_repaired_count = 0
        self._evaluation_unresolved_count = 0
        self._acquisition_attempt_count = 0
        self._acquisition_success_count = 0
        self._acquisition_failure_count = 0
        self._acquisition_symbol_count = 0
        self._load_metrics()

    @staticmethod
    def _symbol(value: str) -> str:
        clean = str(value or "").strip().upper()
        if ":" in clean:
            clean = clean.rsplit(":", 1)[-1]
        return "".join(ch for ch in clean if ch.isalnum() or ch in {".", "-"}) or "UNKNOWN"

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Yahoo evidence timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _day_path(self, symbol: str, session_date: date) -> Path:
        safe = self._symbol(symbol)
        digest = hashlib.sha256(safe.encode("utf-8")).hexdigest()[:16]
        return self.root / "bars" / f"{safe}-{digest}" / f"{session_date.isoformat()}.json"

    def _metrics_path(self) -> Path:
        return self.root / "diagnostics.json"

    def _session_metrics_path(self, session_date: date) -> Path:
        return self.root / "sessions" / f"{session_date.isoformat()}.json"

    @staticmethod
    def _empty_session_metrics(session_date: date) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": "yahoo",
            "session_date": session_date.isoformat(),
            "evaluation_count": 0,
            "repaired_evaluation_count": 0,
            "genuinely_blocked_evaluation_count": 0,
            "passed_evaluation_count": 0,
            "repaired_but_blocked_evaluation_count": 0,
            "blocked_reason_counts": {},
        }

    def _read_session_metrics(self, session_date: date) -> dict[str, Any]:
        path = self._session_metrics_path(session_date)
        baseline = self._empty_session_metrics(session_date)
        if not path.exists():
            return baseline
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return baseline
        if (
            not isinstance(payload, dict)
            or str(payload.get("session_date") or "") != session_date.isoformat()
        ):
            return baseline
        for name in (
            "evaluation_count",
            "repaired_evaluation_count",
            "genuinely_blocked_evaluation_count",
            "passed_evaluation_count",
            "repaired_but_blocked_evaluation_count",
        ):
            try:
                baseline[name] = max(0, int(payload.get(name, 0) or 0))
            except (TypeError, ValueError):
                baseline[name] = 0
        reasons = payload.get("blocked_reason_counts")
        if isinstance(reasons, dict):
            normalized: dict[str, int] = {}
            for raw_reason, raw_count in reasons.items():
                reason = str(raw_reason or "").strip() or "RECOVERY_UNRESOLVED"
                try:
                    count = max(0, int(raw_count or 0))
                except (TypeError, ValueError):
                    continue
                if count:
                    normalized[reason] = count
            baseline["blocked_reason_counts"] = dict(sorted(normalized.items()))
        updated_at = payload.get("updated_at")
        if isinstance(updated_at, str) and updated_at:
            baseline["updated_at"] = updated_at
        return baseline

    def _record_session_evaluation(
        self,
        session_date: date,
        *,
        repaired: bool,
        unresolved: bool,
        reason: str | None,
    ) -> None:
        path = self._session_metrics_path(session_date)
        lock_path = path.with_suffix(".lock")
        with _interprocess_file_lock(lock_path):
            payload = self._read_session_metrics(session_date)
            payload["evaluation_count"] = int(payload["evaluation_count"]) + 1
            if repaired:
                payload["repaired_evaluation_count"] = (
                    int(payload["repaired_evaluation_count"]) + 1
                )
            if unresolved:
                payload["genuinely_blocked_evaluation_count"] = (
                    int(payload["genuinely_blocked_evaluation_count"]) + 1
                )
                if repaired:
                    payload["repaired_but_blocked_evaluation_count"] = (
                        int(payload["repaired_but_blocked_evaluation_count"]) + 1
                    )
                reason_key = str(reason or "").strip() or "RECOVERY_UNRESOLVED"
                reasons = dict(payload.get("blocked_reason_counts") or {})
                reasons[reason_key] = int(reasons.get(reason_key, 0) or 0) + 1
                payload["blocked_reason_counts"] = dict(sorted(reasons.items()))
            else:
                payload["passed_evaluation_count"] = (
                    int(payload["passed_evaluation_count"]) + 1
                )
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(
                f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)

    def _metrics_payload(self) -> dict[str, int]:
        return {
            "persisted_bar_count": self._persisted_bar_count,
            "loaded_bar_count": self._loaded_bar_count,
            "repair_attempt_count": self._repair_attempt_count,
            "repair_success_count": self._repair_success_count,
            "repaired_bar_count": self._repaired_bar_count,
            "unresolved_repair_count": self._unresolved_repair_count,
            "rvol_baseline_hit_count": self._rvol_baseline_hit_count,
            "rvol_baseline_miss_count": self._rvol_baseline_miss_count,
            "causal_replay_rejection_count": self._causal_replay_rejection_count,
            "evaluation_repaired_count": self._evaluation_repaired_count,
            "evaluation_unresolved_count": self._evaluation_unresolved_count,
            "acquisition_attempt_count": self._acquisition_attempt_count,
            "acquisition_success_count": self._acquisition_success_count,
            "acquisition_failure_count": self._acquisition_failure_count,
            "acquisition_symbol_count": self._acquisition_symbol_count,
        }

    def _load_metrics(self) -> None:
        path = self._metrics_path()
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for name in self._metrics_payload():
            try:
                setattr(self, f"_{name}", max(0, int(payload.get(name, 0) or 0)))
            except (TypeError, ValueError):
                continue

    def _persist_metrics(self) -> None:
        path = self._metrics_path()
        lock_path = path.with_suffix(".lock")
        with _interprocess_file_lock(lock_path):
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            temporary.write_text(
                json.dumps(self._metrics_payload(), sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)

    @staticmethod
    def _empty_payload(symbol: str, session_date: date) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": "yahoo",
            "symbol": symbol,
            "session_date": session_date.isoformat(),
            "bars": {},
        }

    def _load_payload(self, path: Path, symbol: str, session_date: date) -> dict[str, Any]:
        if not path.exists():
            return self._empty_payload(symbol, session_date)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._empty_payload(symbol, session_date)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            return self._empty_payload(symbol, session_date)
        if str(payload.get("symbol") or "").upper() != symbol.upper():
            return self._empty_payload(symbol, session_date)
        return payload

    @staticmethod
    def _record_from_market_bar(bar: MarketBar) -> dict[str, Any]:
        return {
            "start_time": bar.start_time.astimezone(timezone.utc).isoformat(),
            "end_time": bar.end_time.astimezone(timezone.utc).isoformat(),
            "open": str(bar.open),
            "high": str(bar.high),
            "low": str(bar.low),
            "close": str(bar.close),
            "volume": str(bar.volume),
            "session": bar.session,
            "provider_event_id": bar.provider_event_id,
            "received_at": bar.received_at.astimezone(timezone.utc).isoformat(),
        }

    @staticmethod
    def _record_rank(record: dict[str, Any]) -> tuple[str, str]:
        return (
            str(record.get("received_at") or ""),
            str(record.get("provider_event_id") or ""),
        )

    def _persist_records(
        self,
        symbol: str,
        grouped: dict[date, list[dict[str, Any]]],
    ) -> int:
        written = 0
        normalized_symbol = self._symbol(symbol)
        with self._lock:
            for session_date, records in grouped.items():
                path = self._day_path(normalized_symbol, session_date)
                lock_path = path.with_suffix(".lock")
                with _interprocess_file_lock(lock_path):
                    payload = self._load_payload(path, normalized_symbol, session_date)
                    bars = dict(payload.get("bars") or {})
                    for record in records:
                        key = str(record["start_time"])
                        previous = bars.get(key)
                        if not isinstance(previous, dict) or self._record_rank(record) >= self._record_rank(previous):
                            if previous != record:
                                bars[key] = record
                                written += 1
                    payload["bars"] = bars
                    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(
                        f".{os.getpid()}.{threading.get_ident()}.tmp"
                    )
                    temporary.write_text(
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        encoding="utf-8",
                    )
                    temporary.replace(path)
            self._persisted_bar_count += written
            if written:
                self._persist_metrics()
        return written

    def persist_market_bars(self, bars: list[MarketBar] | tuple[MarketBar, ...]) -> int:
        grouped: dict[str, dict[date, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for bar in bars:
            if bar.provider != "yahoo" or bar.interval != "1m" or not bar.is_final:
                continue
            symbol = self._symbol(bar.instrument_id)
            local_date = bar.start_time.astimezone(_ET).date()
            grouped[symbol][local_date].append(self._record_from_market_bar(bar))
        total = 0
        for symbol, by_date in grouped.items():
            total += self._persist_records(symbol, by_date)
        return total

    def persist_chart_result(
        self,
        symbol: str,
        result: dict[str, Any],
        *,
        received_at: datetime,
        cutoff: datetime | None = None,
    ) -> int:
        """Persist finalized raw Yahoo 1m chart rows before an instrument is registered."""

        received = self._utc(received_at)
        cutoff_utc = self._utc(cutoff) if cutoff is not None else received
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        if not isinstance(quote, dict):
            return 0
        timestamps = result.get("timestamp") or []
        arrays = {name: quote.get(name) or [] for name in ("open", "high", "low", "close", "volume")}
        if not isinstance(timestamps, list):
            return 0

        grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for index, raw_timestamp in enumerate(timestamps):
            try:
                values = {name: arrays[name][index] for name in arrays}
            except (IndexError, TypeError):
                continue
            if any(values[name] is None for name in ("open", "high", "low", "close")):
                continue
            try:
                start = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)
                end = start + timedelta(minutes=1)
                open_value = Decimal(str(values["open"]))
                high = Decimal(str(values["high"]))
                low = Decimal(str(values["low"]))
                close = Decimal(str(values["close"]))
                volume = Decimal(str(values["volume"] or 0))
            except Exception:
                continue
            if end > cutoff_utc:
                continue
            if not all(value.is_finite() for value in (open_value, high, low, close, volume)):
                continue
            if high < max(open_value, close) or low > min(open_value, close) or volume < 0:
                continue
            local = start.astimezone(_ET)
            clock = local.timetz().replace(tzinfo=None)
            if clock < _REGULAR_OPEN:
                session = "extended_pre"
            elif clock >= time(16, 0):
                session = "extended_post"
            else:
                session = "regular"
            grouped[local.date()].append(
                {
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "open": str(open_value),
                    "high": str(high),
                    "low": str(low),
                    "close": str(close),
                    "volume": str(volume),
                    "session": session,
                    "provider_event_id": str(raw_timestamp),
                    "received_at": received.isoformat(),
                }
            )
        return self._persist_records(self._symbol(symbol), grouped)

    def _records_for_date(self, symbol: str, session_date: date) -> list[dict[str, Any]]:
        path = self._day_path(symbol, session_date)
        with self._lock:
            payload = self._load_payload(path, self._symbol(symbol), session_date)
        rows = [row for row in (payload.get("bars") or {}).values() if isinstance(row, dict)]
        return sorted(rows, key=lambda row: str(row.get("start_time") or ""))

    def load_market_bars(
        self,
        instrument_id: str,
        *,
        start: datetime,
        end: datetime,
        session: str | None = None,
        knowledge_mode: KnowledgeMode = "live",
        known_by: datetime | None = None,
    ) -> list[MarketBar]:
        start_utc = self._utc(start)
        end_utc = self._utc(end)
        known_cutoff = self._utc(known_by) if known_by is not None else end_utc
        if end_utc <= start_utc:
            return []
        symbol = self._symbol(instrument_id)
        first_date = start_utc.astimezone(_ET).date()
        last_date = (end_utc - timedelta(microseconds=1)).astimezone(_ET).date()
        current = first_date
        output: list[MarketBar] = []
        while current <= last_date:
            for row in self._records_for_date(symbol, current):
                try:
                    bar_start = datetime.fromisoformat(str(row["start_time"]))
                    bar_end = datetime.fromisoformat(str(row["end_time"]))
                    received = datetime.fromisoformat(str(row["received_at"]))
                except (KeyError, TypeError, ValueError):
                    continue
                if bar_start.tzinfo is None or bar_end.tzinfo is None or received.tzinfo is None:
                    continue
                bar_start = bar_start.astimezone(timezone.utc)
                bar_end = bar_end.astimezone(timezone.utc)
                received = received.astimezone(timezone.utc)
                if not start_utc <= bar_start < end_utc:
                    continue
                if knowledge_mode == "causal_replay" and received > known_cutoff:
                    with self._lock:
                        self._causal_replay_rejection_count += 1
                    continue
                row_session = str(row.get("session") or "regular")
                if session is not None and row_session != session:
                    continue
                try:
                    output.append(
                        MarketBar(
                            instrument_id=instrument_id,
                            interval="1m",
                            start_time=bar_start,
                            end_time=bar_end,
                            open=Decimal(str(row["open"])),
                            high=Decimal(str(row["high"])),
                            low=Decimal(str(row["low"])),
                            close=Decimal(str(row["close"])),
                            volume=Decimal(str(row.get("volume") or "0")),
                            is_final=True,
                            adjustment_mode=AdjustmentMode.RAW,
                            session=row_session,
                            provider="yahoo",
                            provider_event_id=(
                                str(row.get("provider_event_id"))
                                if row.get("provider_event_id") is not None
                                else None
                            ),
                            received_at=received.astimezone(timezone.utc),
                        )
                    )
                except Exception:
                    continue
            current += timedelta(days=1)
        output.sort(key=lambda bar: bar.start_time)
        with self._lock:
            self._loaded_bar_count += len(output)
            self._persist_metrics()
        return output

    @staticmethod
    def _latest_completed_premarket_clock(evaluation_time: datetime) -> time | None:
        local = evaluation_time.astimezone(_ET)
        opening = datetime.combine(local.date(), _PREMARKET_OPEN, tzinfo=_ET)
        if local < opening + timedelta(minutes=1):
            return None
        latest = (local - timedelta(minutes=1)).replace(second=0, microsecond=0)
        if latest.time() >= _REGULAR_OPEN:
            latest = datetime.combine(local.date(), _REGULAR_OPEN, tzinfo=_ET) - timedelta(minutes=1)
        return latest.time()

    def premarket_relative_volume(
        self,
        symbol_or_instrument: str,
        evaluation_time: datetime,
        *,
        minimum_baseline_sessions: int = 5,
        lookback_calendar_days: int = 60,
        minimum_baseline_coverage_ratio: Decimal = Decimal("0.90"),
        knowledge_mode: KnowledgeMode = "live",
    ) -> YahooRelativeVolumeEvidence:
        if evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware")
        observed = evaluation_time.astimezone(timezone.utc)
        local = observed.astimezone(_ET)
        cutoff = self._latest_completed_premarket_clock(observed)
        symbol = self._symbol(symbol_or_instrument)
        expected = 0
        if cutoff is not None:
            expected = (
                cutoff.hour * 60
                + cutoff.minute
                - (_PREMARKET_OPEN.hour * 60 + _PREMARKET_OPEN.minute)
                + 1
            )

        def session_totals(session_date: date) -> tuple[Decimal, Decimal, int, int]:
            volume = Decimal("0")
            dollar = Decimal("0")
            count = 0
            nonzero = 0
            if cutoff is None:
                return volume, dollar, count, nonzero
            for row in self._records_for_date(symbol, session_date):
                if str(row.get("session") or "") != "extended_pre":
                    continue
                try:
                    start = datetime.fromisoformat(str(row["start_time"])).astimezone(_ET)
                    received = datetime.fromisoformat(str(row["received_at"])).astimezone(timezone.utc)
                    value = Decimal(str(row.get("volume") or "0"))
                    close = Decimal(str(row.get("close") or "0"))
                except Exception:
                    continue
                if knowledge_mode == "causal_replay" and received > observed:
                    continue
                if start.timetz().replace(tzinfo=None) > cutoff:
                    continue
                count += 1
                volume += max(Decimal("0"), value)
                if value > 0:
                    nonzero += 1
                if close > 0 and value > 0:
                    dollar += value * close
            return volume, dollar, count, nonzero

        current_volume, current_dollar, current_count, current_nonzero = session_totals(
            local.date()
        )
        historical: list[Decimal] = []
        rejected_baseline_sessions = 0
        cursor = local.date() - timedelta(days=1)
        floor = local.date() - timedelta(days=max(1, lookback_calendar_days))
        while cursor >= floor:
            volume, _, count, _ = session_totals(cursor)
            coverage = (
                Decimal(count) / Decimal(expected)
                if expected > 0
                else Decimal("0")
            )
            if (
                count > 0
                and volume > 0
                and coverage >= minimum_baseline_coverage_ratio
            ):
                historical.append(volume)
            elif count > 0:
                rejected_baseline_sessions += 1
            cursor -= timedelta(days=1)
        historical = historical[:30]
        baseline_count = len(historical)
        baseline = (
            sum(historical, Decimal("0")) / Decimal(baseline_count)
            if baseline_count
            else None
        )
        relative = (
            current_volume / baseline
            if baseline is not None
            and baseline > 0
            and baseline_count >= minimum_baseline_sessions
            else None
        )
        coverage = (
            Decimal(current_count) / Decimal(expected)
            if expected > 0
            else None
        )
        with self._lock:
            if relative is None:
                self._rvol_baseline_miss_count += 1
            else:
                self._rvol_baseline_hit_count += 1
            self._persist_metrics()
        return YahooRelativeVolumeEvidence(
            symbol=symbol,
            observed_at=observed,
            cutoff_clock=cutoff.isoformat(timespec="minutes") if cutoff is not None else "",
            current_volume=current_volume,
            current_dollar_volume=current_dollar,
            baseline_mean_volume=baseline,
            baseline_session_count=baseline_count,
            rejected_baseline_session_count=rejected_baseline_sessions,
            baseline_min_coverage_ratio=minimum_baseline_coverage_ratio,
            relative_volume=relative,
            current_bar_count=current_count,
            current_nonzero_bar_count=current_nonzero,
            expected_bar_count=expected,
            coverage_ratio=coverage,
        )

    def record_repair(
        self,
        *,
        attempted: bool,
        recovered_bar_count: int,
        unresolved: bool,
    ) -> None:
        with self._lock:
            if attempted:
                self._repair_attempt_count += 1
            if recovered_bar_count > 0:
                self._repair_success_count += 1
                self._repaired_bar_count += int(recovered_bar_count)
            if unresolved:
                self._unresolved_repair_count += 1
            self._persist_metrics()

    def record_acquisition(
        self,
        *,
        attempted: int = 0,
        succeeded: int = 0,
        failed: int = 0,
        symbols: int = 0,
    ) -> None:
        with self._lock:
            self._acquisition_attempt_count += max(0, int(attempted))
            self._acquisition_success_count += max(0, int(succeeded))
            self._acquisition_failure_count += max(0, int(failed))
            self._acquisition_symbol_count += max(0, int(symbols))
            self._persist_metrics()

    def record_evaluation_outcome(
        self,
        *,
        repaired: bool,
        unresolved: bool,
        session_date: date | None = None,
        reason: str | None = None,
    ) -> None:
        effective_session_date = session_date or datetime.now(timezone.utc).astimezone(_ET).date()
        with self._lock:
            if repaired:
                self._evaluation_repaired_count += 1
            if unresolved:
                self._evaluation_unresolved_count += 1
            self._persist_metrics()
            self._record_session_evaluation(
                effective_session_date,
                repaired=repaired,
                unresolved=unresolved,
                reason=reason,
            )

    def session_diagnostics(self, session_date: date) -> dict[str, object]:
        with self._lock:
            return dict(self._read_session_metrics(session_date))

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            current_session_date = datetime.now(timezone.utc).astimezone(_ET).date()
            return {
                "policy": "yahoo-evidence-recovery-v1",
                "provider": "yahoo",
                "volume_authority": "provider_relative",
                "consolidated_volume_authority": False,
                "execution_authority": False,
                "root": str(self.root),
                "persisted_bar_count": self._persisted_bar_count,
                "loaded_bar_count": self._loaded_bar_count,
                "repair_attempt_count": self._repair_attempt_count,
                "repair_success_count": self._repair_success_count,
                "repaired_bar_count": self._repaired_bar_count,
                "unresolved_repair_count": self._unresolved_repair_count,
                "rvol_baseline_hit_count": self._rvol_baseline_hit_count,
                "rvol_baseline_miss_count": self._rvol_baseline_miss_count,
                "causal_replay_rejection_count": self._causal_replay_rejection_count,
                "evaluation_repaired_count": self._evaluation_repaired_count,
                "evaluation_unresolved_count": self._evaluation_unresolved_count,
                "acquisition_attempt_count": self._acquisition_attempt_count,
                "acquisition_success_count": self._acquisition_success_count,
                "acquisition_failure_count": self._acquisition_failure_count,
                "acquisition_symbol_count": self._acquisition_symbol_count,
                "current_session_metrics": self._read_session_metrics(current_session_date),
                "metrics_persistent": True,
                "session_metrics_persistent": True,
                "interprocess_write_locking": True,
            }


_default_store: YahooEvidenceStore | None = None
_default_lock = threading.Lock()


def default_yahoo_evidence_store() -> YahooEvidenceStore:
    global _default_store
    if _default_store is None:
        with _default_lock:
            if _default_store is None:
                _default_store = YahooEvidenceStore()
    return _default_store


__all__ = [
    "YahooEvidenceStore",
    "YahooRelativeVolumeEvidence",
    "YahooVolumeAuthority",
    "KnowledgeMode",
    "default_yahoo_evidence_store",
]
