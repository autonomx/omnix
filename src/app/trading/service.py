from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from datetime import date, datetime, time, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from .cache import TradingMarketDataCache
from .execution import ExecutionEligibilityPolicy, ExecutionObservation
from .market_data_recovery import (
    KnowledgeMode,
    RecoveredBars,
    aggregate_complete_bars,
    deduplicate_bars,
    detect_session_gaps,
    reconcile_recovery,
)
from .models import FeedType, MarketBar
from .providers.binance import BinanceMarketDataProvider
from .providers.alpaca_iex_status import default_alpaca_iex_status_cache
from .providers.bar_semantics import interval_duration
from .providers.registry import ProviderRegistry
from .streaming.binance_stream import BinanceWebSocketStream
from .streaming.manager import SharedSubscriptionManager, StreamingBarUpdate
from .yahoo_evidence import YahooEvidenceStore, default_yahoo_evidence_store


class TradingMarketDataService:
    def __init__(
        self,
        *,
        provider: BinanceMarketDataProvider | None = None,
        registry: ProviderRegistry | None = None,
        cache: TradingMarketDataCache | None = None,
        subscriptions: SharedSubscriptionManager | None = None,
        stream: BinanceWebSocketStream | None = None,
        yahoo_evidence_store: YahooEvidenceStore | None = None,
    ) -> None:
        self.cache = cache or TradingMarketDataCache(
            max_entries=256,
            cache_dir=Path("resources/cache/trading"),
        )
        self.registry = registry or ProviderRegistry(cache=self.cache)
        if provider is not None:
            self.registry._providers["binance"] = provider
        self.provider = self.registry.provider("binance")
        self.subscriptions = subscriptions or SharedSubscriptionManager()
        self.stream = stream or BinanceWebSocketStream()
        self.yahoo_evidence_store = yahoo_evidence_store or default_yahoo_evidence_store()

    def bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int = 500,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ):
        return self.registry.bars(
            instrument_id,
            interval,
            limit,
            binding_id,
            cancellation,
        )

    def recovered_bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int = 500,
        binding_id: str | None = None,
        *,
        session_date: date,
        as_of: datetime,
        max_primary_attempts: int = 2,
        cancellation: threading.Event | None = None,
        knowledge_mode: KnowledgeMode = "live",
        knowledge_cutoff: datetime | None = None,
    ) -> RecoveredBars:
        """Return the shared causal tape for every strategy consumer.

        Yahoo intraday recovery is canonicalized at 1m before any coarser
        aggregation: ordinary response + durable evidence + exact repair are
        deduplicated into one Yahoo tape, then aggregated once. IEX is considered
        only for still-missing buckets and remains partial-market evidence.
        """

        if as_of.tzinfo is None:
            raise ValueError("recovered_bars as_of must be timezone-aware")
        observed = as_of.astimezone(timezone.utc)
        known_by = (
            knowledge_cutoff.astimezone(timezone.utc)
            if knowledge_cutoff is not None
            else observed
        )
        attempts = max(1, min(int(max_primary_attempts), 2))
        requested = self.registry.resolve_binding(instrument_id, binding_id)
        primary_provider = requested.provider
        primary_response = None
        primary_error: str | None = None
        primary_attempt_count = 0
        yahoo_intraday = bool(
            primary_provider == "yahoo"
            and instrument_id.startswith("equity:")
            and (interval.endswith("m") or interval.endswith("h"))
        )

        primary_bars: list[MarketBar] = []
        yahoo_1m: list[MarketBar] = []
        request_interval = "1m" if yahoo_intraday else interval
        request_limit = (
            min(2_000, max(500, limit * 60))
            if yahoo_intraday and interval != "1m"
            else limit
        )
        for _ in range(attempts):
            primary_attempt_count += 1
            try:
                response = self.registry.bars(
                    instrument_id,
                    request_interval,
                    request_limit,
                    requested.binding_id,
                    cancellation,
                )
            except Exception as exc:
                primary_error = f"{type(exc).__name__}: {exc}"
                continue
            if yahoo_intraday:
                yahoo_1m.extend(list(response.bars))
                primary_response = response if interval == "1m" else None
            else:
                primary_bars.extend(list(response.bars))
                primary_response = response
            # Yahoo gets durable/exact union below; a successful response is
            # enough to stop repeated whole-dataset acquisition here.
            if yahoo_intraday:
                break
            if not detect_session_gaps(
                primary_bars,
                session_date=session_date,
                interval=interval,
                as_of=observed,
                knowledge_mode=knowledge_mode,
                knowledge_cutoff=known_by,
            ):
                break

        yahoo_repair_attempted = False
        yahoo_repaired_count = 0
        if yahoo_intraday:
            et = ZoneInfo("America/New_York")
            session_open = datetime.combine(
                session_date, time(9, 30), tzinfo=et
            ).astimezone(timezone.utc)
            session_close = datetime.combine(
                session_date, time(16, 0), tzinfo=et
            ).astimezone(timezone.utc)
            bounded_end = min(observed, session_close)
            if bounded_end > session_open:
                yahoo_1m.extend(
                    self.yahoo_evidence_store.load_market_bars(
                        instrument_id,
                        start=session_open,
                        end=bounded_end,
                        session="regular",
                        knowledge_mode=knowledge_mode,
                        known_by=known_by,
                    )
                )

            def project_yahoo() -> list[MarketBar]:
                canonical_1m = deduplicate_bars(
                    yahoo_1m,
                    preferred_provider="yahoo",
                )
                if interval == "1m":
                    return canonical_1m
                return aggregate_complete_bars(
                    canonical_1m,
                    session_date=session_date,
                    target_interval=interval,
                    as_of=observed,
                    knowledge_mode=knowledge_mode,
                    knowledge_cutoff=known_by,
                )

            try:
                primary_bars = project_yahoo()
            except ValueError as exc:
                primary_error = (
                    f"{primary_error}; yahoo_1m_aggregation={exc}"
                    if primary_error
                    else f"yahoo_1m_aggregation={exc}"
                )
                primary_bars = []

            before_gaps = detect_session_gaps(
                primary_bars,
                session_date=session_date,
                interval=interval,
                as_of=observed,
                knowledge_mode=knowledge_mode,
                knowledge_cutoff=known_by,
            )
            before_missing = sum(gap.missing_bar_count for gap in before_gaps)

            # A fresh request observed now cannot repair a historical causal
            # replay decision. Preserve that as explicit retroactive research.
            if before_gaps and knowledge_mode != "causal_replay":
                yahoo_provider = self.registry.provider("yahoo")
                repair = getattr(yahoo_provider, "get_intraday_bars_range", None)
                if callable(repair):
                    yahoo_repair_attempted = True
                    repair_start = min(gap.start for gap in before_gaps)
                    repair_end = max(gap.end for gap in before_gaps)
                    try:
                        exact = repair(
                            instrument_id,
                            start=repair_start,
                            end=repair_end,
                            include_extended_hours=False,
                            cancellation=cancellation,
                        )
                        yahoo_1m.extend(list(exact.bars))
                        primary_bars = project_yahoo()
                    except Exception as exc:
                        detail = f"{type(exc).__name__}: {exc}"
                        primary_error = (
                            f"{primary_error}; yahoo_exact_repair={detail}"
                            if primary_error
                            else f"yahoo_exact_repair={detail}"
                        )

            after_yahoo = detect_session_gaps(
                primary_bars,
                session_date=session_date,
                interval=interval,
                as_of=observed,
                knowledge_mode=knowledge_mode,
                knowledge_cutoff=known_by,
            )
            after_missing = sum(gap.missing_bar_count for gap in after_yahoo)
            yahoo_repaired_count = max(0, before_missing - after_missing)

        primary_gaps = detect_session_gaps(
            primary_bars,
            session_date=session_date,
            interval=interval,
            as_of=observed,
            knowledge_mode=knowledge_mode,
            knowledge_cutoff=known_by,
        )

        # Missing bars can be classified as confirmed halt/no-trade only by an
        # independent status authority. Unknown market state remains unresolved.
        confirmed_nontrading: list[datetime] = []
        unresolved_market_state: list[datetime] = []
        if instrument_id.startswith("equity:") and primary_gaps:
            symbol = instrument_id.rsplit(":", 1)[-1]
            status_cache = default_alpaca_iex_status_cache()
            duration = interval_duration(interval)
            for gap in primary_gaps:
                cursor = gap.start
                while cursor < gap.end:
                    if status_cache.confirmed_halt_interval(
                        symbol,
                        start=cursor,
                        end=cursor + duration,
                    ):
                        confirmed_nontrading.append(cursor)
                    else:
                        unresolved_market_state.append(cursor)
                    cursor += duration

        fallback_attempted = False
        fallback_provider: str | None = None
        fallback_bars: list[MarketBar] = []
        fallback_error: str | None = None
        fallback_binding_id: str | None = None
        unconfirmed_gap_starts = set(unresolved_market_state)
        if primary_gaps and not instrument_id.startswith("equity:"):
            duration = interval_duration(interval)
            for gap in primary_gaps:
                cursor = gap.start
                while cursor < gap.end:
                    unconfirmed_gap_starts.add(cursor)
                    cursor += duration
        if primary_gaps and unconfirmed_gap_starts:
            try:
                execution_binding = self.registry.resolve_execution_binding(
                    instrument_id,
                    requested.binding_id,
                )
                fallback_provider = execution_binding.provider
                fallback_binding_id = execution_binding.binding_id
                if fallback_provider != primary_provider:
                    fallback_attempted = True
                    one_minute = self.registry.execution_indicator_bars(
                        instrument_id,
                        requested.binding_id,
                        as_of=observed,
                        cancellation=cancellation,
                    )
                    if interval == "1m":
                        fallback_bars = list(one_minute)
                    else:
                        fallback_bars = aggregate_complete_bars(
                            one_minute,
                            session_date=session_date,
                            target_interval=interval,
                            as_of=observed,
                            knowledge_mode=knowledge_mode,
                            knowledge_cutoff=known_by,
                        )
            except Exception as exc:
                fallback_error = f"{type(exc).__name__}: {exc}"

        recovered = reconcile_recovery(
            instrument_id=instrument_id,
            interval=interval,
            session_date=session_date,
            as_of=observed,
            primary_bars=primary_bars,
            fallback_bars=fallback_bars,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            requested_binding=requested.binding_id,
            resolved_binding=(
                fallback_binding_id
                if fallback_attempted and fallback_bars
                else requested.binding_id
            ),
            primary_attempt_count=primary_attempt_count,
            fallback_attempted=fallback_attempted,
            primary_error=primary_error,
            fallback_error=fallback_error,
            partial_market_fallback=fallback_provider == "alpaca_iex",
            primary_response=primary_response,
            knowledge_mode=knowledge_mode,
            knowledge_cutoff=known_by,
            confirmed_nontrading_starts=confirmed_nontrading,
            unresolved_market_state_starts=unresolved_market_state,
        )
        if primary_provider == "yahoo":
            unresolved_effective = [
                gap
                for gap in recovered.report.unresolved_gaps
                if gap.start not in set(confirmed_nontrading)
            ]
            self.yahoo_evidence_store.record_repair(
                attempted=yahoo_repair_attempted,
                recovered_bar_count=yahoo_repaired_count,
                unresolved=bool(unresolved_effective),
            )
        return recovered

    def yahoo_relative_volume(
        self,
        instrument_id: str,
        evaluation_time: datetime,
        *,
        minimum_baseline_sessions: int = 5,
    ):
        return self.yahoo_evidence_store.premarket_relative_volume(
            instrument_id,
            evaluation_time,
            minimum_baseline_sessions=minimum_baseline_sessions,
        )

    def quote(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        return self.registry.quote(instrument_id, binding_id, cancellation)

    def execution_observation(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        *,
        policy: ExecutionEligibilityPolicy | None = None,
        cancellation: threading.Event | None = None,
    ) -> ExecutionObservation:
        return self.registry.execution_observation(
            instrument_id,
            binding_id,
            policy=policy,
            cancellation=cancellation,
        )

    def execution_indicator_bars(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        *,
        as_of: datetime,
        cancellation: threading.Event | None = None,
    ) -> list[MarketBar]:
        return self.registry.execution_indicator_bars(
            instrument_id,
            binding_id,
            as_of=as_of,
            cancellation=cancellation,
        )

    def currency_rate(
        self,
        base_currency: str,
        quote_currency: str,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        return self.registry.currency_rate(base_currency, quote_currency, cancellation)

    async def stream_updates(
        self,
        instrument_id: str,
        interval: str,
        binding_id: str | None = None,
    ) -> AsyncIterator[StreamingBarUpdate]:
        binding = self.registry.resolve_binding(instrument_id, binding_id)
        if binding.provider != "binance" or binding.feed_type is not FeedType.WEBSOCKET_AND_REST:
            raise ValueError(
                f"binding does not support Omnix live streaming: {binding.binding_id}"
            )
        async for update in self.stream.messages(
            provider_symbol=binding.provider_symbol,
            binding_id=binding.binding_id,
            instrument_id=instrument_id,
            interval=interval,
        ):
            yield update

    def provider_descriptors(self) -> list[dict[str, object]]:
        return self.registry.descriptors()

    def diagnostics(self) -> dict[str, Any]:
        providers = self.provider_descriptors()
        return {
            "providers": [
                {
                    "provider": item["provider"],
                    "status": item["status"],
                    "binding_count": len(item["bindings"]),
                    "official": item["policy"].is_official_api,
                    "usage_scope": item["policy"].usage_scope,
                    "runtime": item.get("runtime", {}),
                }
                for item in providers
            ],
            "cache": {
                "authority": False,
                "disposable": True,
                "directory": str(self.cache.cache_dir) if self.cache.cache_dir else None,
                "max_entries": self.cache.max_entries,
                "disk_bounded": True,
                "atomic_writes": True,
            },
            "execution": {
                "policy_version": ExecutionEligibilityPolicy().policy_version,
                "fail_closed": True,
                "synthetic_reference_prices_allowed": False,
            },
            "yahoo_hardening": self.yahoo_evidence_store.diagnostics(),
            "streams": self.subscriptions.status(),
            "upstream_subscription_count": self.subscriptions.upstream_subscription_count,
        }


_default_service: TradingMarketDataService | None = None
_default_lock = Lock()


def default_market_data_service() -> TradingMarketDataService:
    global _default_service
    if _default_service is None:
        with _default_lock:
            if _default_service is None:
                _default_service = TradingMarketDataService()
    return _default_service
