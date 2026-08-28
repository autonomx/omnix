"""Read-only trading market-data adapter for governed Agent evidence."""
from __future__ import annotations

from app.assistant_tools.models import AssistantToolRequest, AssistantToolResult


def run_trading_tool_request(
    request: AssistantToolRequest,
    *,
    provider=None,
) -> AssistantToolResult:
    if request.action_id != "trading.market_quote":
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            state_changed=False,
            result_summary="Trading action is not available.",
            error="trading_action_not_available",
        )

    ticker = str(
        request.input.get("ticker")
        or request.input.get("symbol")
        or ""
    ).strip().upper().removeprefix("$")
    if not ticker:
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            state_changed=False,
            result_summary="A ticker is required.",
            error="trading_ticker_required",
        )

    try:
        from app.trading.catalog import search_instruments
        from app.trading.models import AssetClass
        from app.trading.providers.alpaca_iex import AlpacaIexExecutionProvider

        candidates = [
            item
            for item in search_instruments(ticker)
            if item.asset_class is AssetClass.EQUITY
            and item.display_symbol.upper() == ticker
        ]
        if len(candidates) != 1:
            return AssistantToolResult(
                tool_id=request.tool_id,
                action_id=request.action_id,
                session_id=request.session_id,
                state_changed=False,
                result_summary=f"Could not resolve {ticker} to exactly one canonical equity instrument.",
                error="trading_instrument_not_resolved",
            )
        runtime = provider or AlpacaIexExecutionProvider()
        observation = runtime.execution_observation(candidates[0].instrument_id)
    except Exception as exc:
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            state_changed=False,
            result_summary=f"Market quote lookup failed for {ticker}.",
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )

    output = observation.model_dump(mode="json")
    output.update({
        "ticker": ticker,
        "source_class": "market_quote",
        "provider": observation.provider,
        "authoritative_read_only": True,
    })
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        state_changed=False,
        result_summary=(
            f"{ticker} quote from {observation.provider}: "
            f"last {observation.last}, bid {observation.bid}, ask {observation.ask}."
        ),
        output=output,
    )
