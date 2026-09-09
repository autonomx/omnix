"""AI-only 1-minute Solana signal policy.

The policy is deliberately limited to interpreting completed Binance spot
candles. It has no deterministic entry rule and no execution authority.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.providers import ChatMessage
from app.providers.structured.contracts import StructuredMode
from app.providers.structured.schema_projection import project_provider_schema


SOLANA_AI_STRATEGY_ID = "solana-ai-1m-shadow"
SOLANA_AI_STRATEGY_VERSION = "solana-ai-1m-v1"
SOLANA_INSTRUMENT_ID: Literal["crypto:BINANCE:spot:SOL-USDT"] = "crypto:BINANCE:spot:SOL-USDT"
SOLANA_BINDING_ID = "binance:websocket_and_rest:crypto:BINANCE:spot:SOL-USDT"

SolanaAIAction = Literal["enter_long", "hold", "exit_long", "skip"]
SolanaAIMarketRegime = Literal[
    "trend_up",
    "trend_down",
    "range",
    "breakout",
    "breakdown",
    "high_variance",
    "unclear",
]


class SolanaAIDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: Literal["crypto:BINANCE:spot:SOL-USDT"] = SOLANA_INSTRUMENT_ID
    action: SolanaAIAction
    confidence: int = Field(ge=0, le=100)
    market_regime: SolanaAIMarketRegime
    expected_horizon_minutes: int = Field(ge=1, le=240)
    thesis: str = Field(min_length=1, max_length=600)
    reason: str = Field(min_length=1, max_length=600)
    invalidation_price: Decimal | None = Field(default=None, gt=0)
    execution_authority: Literal[False] = False


class SolanaAIBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: SolanaAIDecision


class SolanaAIResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: SolanaAIDecision
    provider: str
    model: str | None = None
    input_characters: int = Field(default=0, ge=0)
    output_characters: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    usage_source: Literal["provider", "estimated"] = "estimated"


def _default_provider():
    from app import shared

    return shared.get_provider()


def _strip_json_fence(value: str) -> str:
    text = str(value or "").strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = text.strip(chr(96)).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _usage_int(usage: Any, *keys: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for key in keys:
        try:
            value = int(str(usage.get(key)))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _normalized_usage(
    usage: Any,
    *,
    input_characters: int,
    output_characters: int,
) -> tuple[int, int, int, Literal["provider", "estimated"]]:
    input_tokens = _usage_int(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_int(usage, "completion_tokens", "output_tokens")
    total_tokens = _usage_int(usage, "total_tokens")
    if input_tokens is not None or output_tokens is not None or total_tokens is not None:
        normalized_input = input_tokens or 0
        normalized_output = output_tokens or 0
        return (
            normalized_input,
            normalized_output,
            total_tokens if total_tokens is not None else normalized_input + normalized_output,
            "provider",
        )
    estimated_input = (input_characters + 3) // 4
    estimated_output = (output_characters + 3) // 4
    return (
        estimated_input,
        estimated_output,
        estimated_input + estimated_output,
        "estimated",
    )


def _bar_payload(bar: Any) -> dict[str, object]:
    return {
        "end_time": bar.end_time.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
    }


def solana_ai_snapshot(
    bars: list[Any],
    *,
    observed_at: datetime,
    quote: dict[str, object] | None = None,
    previous_decision: SolanaAIDecision | None = None,
) -> dict[str, object]:
    """Build the model input without calculating a deterministic signal."""

    recent = bars[-60:]
    closes = [bar.close for bar in recent]
    first_close = closes[0] if closes else None
    last_close = closes[-1] if closes else None
    window_return_pct = (
        (last_close / first_close - Decimal("1")) * Decimal("100")
        if first_close is not None and last_close is not None and first_close > 0
        else None
    )
    return {
        "strategy_id": SOLANA_AI_STRATEGY_ID,
        "strategy_version": SOLANA_AI_STRATEGY_VERSION,
        "instrument_id": SOLANA_INSTRUMENT_ID,
        "venue": "Binance spot",
        "chart_interval": "1m",
        "observed_at": observed_at.isoformat(),
        "completed_candle_count": len(recent),
        "window_return_pct": str(window_return_pct) if window_return_pct is not None else None,
        "current_close": str(last_close) if last_close is not None else None,
        "quote": quote or {},
        "previous_decision": (
            previous_decision.model_dump(mode="json") if previous_decision is not None else None
        ),
        "completed_1m_candles": [_bar_payload(bar) for bar in recent],
        "execution_authority": False,
        "research_only": True,
    }


class SolanaAIAnalyzer:
    def __init__(self, provider_factory=None) -> None:
        self.provider_factory = provider_factory or _default_provider

    def assess(
        self,
        *,
        bars: list[Any],
        observed_at: datetime,
        quote: dict[str, object] | None = None,
        previous_decision: SolanaAIDecision | None = None,
    ) -> SolanaAIResult:
        provider = self.provider_factory()
        if provider is None:
            raise RuntimeError("solana_ai_provider_unavailable")

        snapshot = solana_ai_snapshot(
            bars,
            observed_at=observed_at,
            quote=quote,
            previous_decision=previous_decision,
        )
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are the sole signal model for a paper/shadow Solana spot "
                    "strategy. Analyze only the supplied completed Binance SOL/USDT "
                    "one-minute OHLCV candles and quote. Do not use indicators, "
                    "hard-coded technical rules, outside information, or unstated "
                    "assumptions. This is not live trading: never claim an order was "
                    "placed. Return JSON only with exactly one decision object using "
                    "action enter_long, hold, exit_long, or skip; market_regime "
                    "trend_up, trend_down, range, breakout, breakdown, high_variance, "
                    "or unclear; and execution_authority false. If evidence is "
                    "insufficient, choose skip. An enter_long decision may only be a "
                    "recommendation and must include a causal invalidation_price when "
                    "the supplied candles support one."
                ),
            ),
            ChatMessage(role="user", content=json.dumps(snapshot, sort_keys=True)),
        ]
        input_characters = sum(len(message.content) for message in messages)
        model = getattr(getattr(provider, "config", None), "model", None) or None
        provider_name = str(getattr(provider, "provider_name", "") or type(provider).__name__)
        response_format: dict[str, object]
        if provider_name.strip().casefold() == "chatgpt_codex":
            schema = project_provider_schema(
                SolanaAIBatchResponse.model_json_schema(),
                mode=StructuredMode.JSON_SCHEMA,
                provider_name="chatgpt_codex",
            )
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "solana_ai_batch_response",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            response_format = {"type": "json_object"}
        try:
            response = provider.chat_completion(
                messages=messages,
                model=model,
                stream=False,
                response_format=response_format,
                request_timeout_seconds=45,
                temperature=0,
                max_tokens=500,
            )
        except TypeError:
            response = provider.chat_completion(messages=messages, model=model, stream=False)
        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            raise RuntimeError("solana_ai_provider_returned_no_text")
        output_characters = len(content)
        input_tokens, output_tokens, total_tokens, usage_source = _normalized_usage(
            getattr(response, "usage", None),
            input_characters=input_characters,
            output_characters=output_characters,
        )
        try:
            parsed = SolanaAIBatchResponse.model_validate_json(_strip_json_fence(content))
        except Exception as exc:
            raise RuntimeError("solana_ai_provider_returned_invalid_json") from exc
        decision = parsed.decision
        if decision.instrument_id != SOLANA_INSTRUMENT_ID:
            raise RuntimeError("solana_ai_provider_returned_wrong_instrument")
        return SolanaAIResult(
            decision=decision,
            provider=provider_name,
            model=str(getattr(response, "model", "") or model or "") or None,
            input_characters=input_characters,
            output_characters=output_characters,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usage_source=usage_source,
        )


__all__ = [
    "SOLANA_AI_STRATEGY_ID",
    "SOLANA_AI_STRATEGY_VERSION",
    "SOLANA_BINDING_ID",
    "SOLANA_INSTRUMENT_ID",
    "SolanaAIDecision",
    "SolanaAIResult",
    "SolanaAIAnalyzer",
    "solana_ai_snapshot",
]
