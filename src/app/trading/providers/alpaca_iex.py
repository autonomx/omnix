from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import requests

from app.trading.catalog import POLICIES, bindings_for_instrument
from app.trading.execution import (
    ExecutionEligibilityPolicy,
    ExecutionObservation,
    assess_execution_observation,
    execution_observation_from_quote,
)
from app.trading.models import ProviderBinding

from .alpaca_iex_status import default_alpaca_iex_status_cache
from .errors import ProviderContractError, ProviderDataUnavailableError
from .http_runtime import ProviderHttpRuntime


ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_IEX_PARTIAL_MARKET = True
_ET = ZoneInfo("America/New_York")


def _api_key() -> str:
    return (
        os.environ.get("OMNIX_ALPACA_API_KEY_ID")
        or os.environ.get("APCA_API_KEY_ID")
        or ""
    ).strip()


def _api_secret() -> str:
    return (
        os.environ.get("OMNIX_ALPACA_API_SECRET_KEY")
        or os.environ.get("APCA_API_SECRET_KEY")
        or ""
    ).strip()


def alpaca_iex_configured() -> bool:
    return bool(_api_key() and _api_secret())


def _session(source_time: datetime) -> str:
    local = source_time.astimezone(_ET)
    if local.weekday() >= 5:
        return "closed"
    local_time = local.timetz().replace(tzinfo=None)
    if time(4, 0) <= local_time < time(9, 30):
        return "extended_pre"
    if time(9, 30) <= local_time < time(16, 0):
        return "regular"
    if time(16, 0) <= local_time < time(20, 0):
        return "extended_post"
    return "closed"


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ProviderContractError(f"Alpaca IEX snapshot is missing {field} timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderContractError(f"Alpaca IEX returned invalid {field} timestamp") from exc
    if parsed.tzinfo is None:
        raise ProviderContractError(f"Alpaca IEX {field} timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _round_lot_shares(value: Any) -> Decimal | None:
    """Alpaca stock quote sizes are expressed in 100-share round lots."""
    if value in {None, ""}:
        return None
    try:
        lots = Decimal(str(value))
    except Exception as exc:
        raise ProviderContractError("Alpaca IEX returned invalid quote size") from exc
    if lots < 0:
        raise ProviderContractError("Alpaca IEX quote size cannot be negative")
    return lots * Decimal("100")


class AlpacaIexExecutionProvider:
    """Official Alpaca IEX quote adapter for paper execution only.

    Alpaca Basic/Paper Only accounts expose real-time IEX data rather than the
    consolidated SIP. Omnix therefore records the provider as ``alpaca_iex`` and
    never represents this feed as full-market NBBO coverage.
    """

    provider_id = "alpaca_iex"
    policy = POLICIES[provider_id]

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        runtime: ProviderHttpRuntime | None = None,
        data_url: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.runtime = runtime or ProviderHttpRuntime(
            self.provider_id,
            session=session,
            max_concurrency=4,
        )
        self.session = self.runtime.session
        self.data_url = (
            data_url
            or os.environ.get("OMNIX_ALPACA_DATA_URL")
            or ALPACA_DATA_URL
        ).rstrip("/")
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def get_binding(self, instrument_id: str) -> ProviderBinding:
        binding = next(
            (
                item
                for item in bindings_for_instrument(instrument_id)
                if item.provider == self.provider_id
            ),
            None,
        )
        if binding is None:
            raise ValueError(f"Alpaca IEX does not support instrument: {instrument_id}")
        return binding

    def execution_observation(
        self,
        instrument_id: str,
        *,
        policy: ExecutionEligibilityPolicy | None = None,
        cancellation=None,
    ) -> ExecutionObservation:
        key = _api_key()
        secret = _api_secret()
        if not key or not secret:
            raise ProviderDataUnavailableError(
                "Alpaca IEX credentials are not configured; set "
                "OMNIX_ALPACA_API_KEY_ID and OMNIX_ALPACA_API_SECRET_KEY"
            )

        binding = self.get_binding(instrument_id)
        response = self.runtime.get(
            f"{self.data_url}/v2/stocks/{binding.provider_symbol}/snapshot",
            params={"feed": "iex"},
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
            },
            timeout=10,
            cancellation=cancellation,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderContractError("Alpaca IEX returned invalid snapshot JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderContractError("Alpaca IEX snapshot payload is malformed")

        latest_quote = payload.get("latestQuote")
        latest_trade = payload.get("latestTrade")
        if not isinstance(latest_quote, dict):
            raise ProviderDataUnavailableError("Alpaca IEX snapshot has no latest quote")
        if not isinstance(latest_trade, dict):
            raise ProviderDataUnavailableError("Alpaca IEX snapshot has no latest trade")

        quote_time = _parse_timestamp(latest_quote.get("t"), field="quote")
        trade_time = _parse_timestamp(latest_trade.get("t"), field="trade")
        source_time = min(quote_time, trade_time)

        minute_bar = payload.get("minuteBar")
        bar_start_time: datetime | None = None
        bar_high = None
        bar_low = None
        bar_volume = None
        if isinstance(minute_bar, dict):
            timestamp = minute_bar.get("t")
            if timestamp not in {None, ""}:
                bar_start_time = _parse_timestamp(timestamp, field="minute bar")
            bar_high = minute_bar.get("h")
            bar_low = minute_bar.get("l")
            bar_volume = minute_bar.get("v")

        daily_bar = payload.get("dailyBar")
        cumulative_volume = (
            daily_bar.get("v")
            if isinstance(daily_bar, dict) and daily_bar.get("v") is not None
            else None
        )
        now = self.clock()
        if now.tzinfo is None:
            raise ProviderContractError("Alpaca IEX provider clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        quote: dict[str, object] = {
            "instrument_id": instrument_id,
            "binding_id": binding.binding_id,
            "provider": self.provider_id,
            "bid": latest_quote.get("bp"),
            "ask": latest_quote.get("ap"),
            "bid_size": _round_lot_shares(latest_quote.get("bs")),
            "ask_size": _round_lot_shares(latest_quote.get("as")),
            "last": latest_trade.get("p"),
            "high": bar_high,
            "low": bar_low,
            "bar_volume": bar_volume,
            "bar_start_time": bar_start_time.isoformat() if bar_start_time else None,
            "cumulative_volume": cumulative_volume,
            "source_time": source_time,
            "received_at": now.isoformat(),
            "session": _session(source_time),
            "freshness_mode": "live",
            "halted": default_alpaca_iex_status_cache().halted(binding.provider_symbol),
        }
        try:
            observation = execution_observation_from_quote(
                quote,
                binding_id=binding.binding_id,
                provider=self.provider_id,
                received_at=now,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderContractError("Alpaca IEX snapshot is missing executable prices") from exc
        return assess_execution_observation(observation, policy)
