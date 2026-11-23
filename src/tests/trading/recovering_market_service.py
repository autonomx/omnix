"""The shared test double for a market service's recovered tape.

Strategy and research code reads current-session bars through
``TradingMarketDataService.recovered_bars`` (and warms them with
``prefetch_recovered_bars``); neither is optional. A test double that only
knows how to answer ``bars(...)`` mixes this in: ``recovered_bars`` asks the
double's own ``bars`` once and reconciles the answer with the production
``reconcile_recovery``, so the caller sees the same finalized, deduplicated,
gap-reported tape it would see in production. A failing ``bars`` is reported as
``primary_error`` with no bars, as the service reports it, rather than raised.
"""
from __future__ import annotations

from typing import Any

from app.apps.trading.market_data_recovery import RecoveredBars, reconcile_recovery


class RecoveringMarketService:
    """Mixin for a market-service double whose ``bars(...)`` is the primary provider."""

    recovery_primary_provider: str | None = None

    def recovered_bars(
        self,
        instrument_id,
        interval,
        limit=500,
        binding_id=None,
        *,
        session_date,
        as_of,
        max_primary_attempts=2,
        cancellation=None,
        knowledge_mode="live",
        knowledge_cutoff=None,
    ) -> RecoveredBars:
        primary_error: str | None = None
        response: Any = None
        try:
            response = self.bars(instrument_id, interval, limit, binding_id)  # type: ignore[attr-defined]
        except Exception as exc:
            primary_error = f"{type(exc).__name__}: {exc}"
        bars = list(getattr(response, "bars", ()) or ())
        provenance = getattr(response, "provenance", None)
        provider = self.recovery_primary_provider or getattr(provenance, "provider", None) or (
            bars[0].provider if bars else None
        )
        return reconcile_recovery(
            instrument_id=instrument_id,
            interval=interval,
            session_date=session_date,
            as_of=as_of,
            primary_bars=bars,
            primary_provider=provider,
            requested_binding=binding_id,
            resolved_binding=getattr(provenance, "resolved_binding", None) or binding_id,
            primary_error=primary_error,
            primary_response=response,
            knowledge_mode=knowledge_mode,
            knowledge_cutoff=knowledge_cutoff,
        )

    def prefetch_recovered_bars(self, requests, *, session_date, as_of, workers=4) -> None:
        """Warming is a cache optimisation in production; a double has no cache to warm."""
        return None


__all__ = ["RecoveringMarketService"]
