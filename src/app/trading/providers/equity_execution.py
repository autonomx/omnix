from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.trading.execution import (
    ExecutionEligibilityPolicy,
    ExecutionObservation,
    assess_execution_observation,
    execution_observation_from_quote,
)

from .errors import ProviderContractError, ProviderDataUnavailableError


YAHOO_EXECUTION_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"


def _session(market_state: str) -> str:
    state = market_state.strip().upper()
    if state in {"PRE", "PREPRE"}:
        return "extended_pre"
    if state in {"POST", "POSTPOST"}:
        return "extended_post"
    if state == "REGULAR":
        return "regular"
    if state in {"CLOSED", "CLOSE"}:
        return "closed"
    return "unknown"


def yahoo_execution_observation(
    provider: Any,
    instrument_id: str,
    *,
    policy: ExecutionEligibilityPolicy | None = None,
    cancellation=None,
) -> ExecutionObservation:
    """Fetch an uncached Yahoo quote and assess it under the fail-closed execution policy."""

    binding = provider.get_binding(instrument_id)
    response = provider.runtime.get(
        YAHOO_EXECUTION_QUOTE_URL,
        params={"symbols": binding.provider_symbol},
        headers={"User-Agent": "Mozilla/5.0 Omnix local research"},
        timeout=10,
        cancellation=cancellation,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderContractError("Yahoo returned invalid execution quote JSON") from exc
    result = ((payload.get("quoteResponse") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        raise ProviderDataUnavailableError("Yahoo returned no execution quote")
    last = result.get("regularMarketPrice") or result.get("postMarketPrice") or result.get("preMarketPrice")
    if last in {None, 0, "0"}:
        raise ProviderDataUnavailableError("Yahoo execution quote has no market price")
    source_timestamp = (
        result.get("regularMarketTime")
        or result.get("postMarketTime")
        or result.get("preMarketTime")
    )
    now = datetime.now(timezone.utc)
    quote: dict[str, object] = {
        "instrument_id": instrument_id,
        "binding_id": binding.binding_id,
        "provider": "yahoo",
        "bid": result.get("bid"),
        "ask": result.get("ask"),
        "last": last,
        "cumulative_volume": result.get("regularMarketVolume"),
        "source_time": source_timestamp or now,
        "received_at": now.isoformat(),
        "session": _session(str(result.get("marketState") or "")),
        "freshness_mode": "polled",
    }
    observation = execution_observation_from_quote(
        quote,
        binding_id=binding.binding_id,
        provider="yahoo",
        received_at=now,
    )
    return assess_execution_observation(observation, policy)
