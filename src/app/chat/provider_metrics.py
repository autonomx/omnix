"""Normalize provider response statistics for persisted chat metadata."""
from __future__ import annotations

from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if parsed == parsed and parsed not in {float("inf"), float("-inf")} else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _finite_number(value)
        if parsed is not None:
            return parsed
    return None


def _first_integer(*values: Any) -> int | None:
    for value in values:
        parsed = _integer(value)
        if parsed is not None:
            return parsed
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def merge_provider_response_metrics(
    current: dict[str, Any] | None,
    response: Any,
    *,
    provider_id: str | None,
) -> dict[str, Any]:
    """Merge usage and LM Studio stats from one provider response or stream chunk."""
    metrics = dict(current or {})
    raw = _mapping(getattr(response, "raw_response", None))
    stats = _mapping(raw.get("stats"))
    usage = _mapping(getattr(response, "usage", None)) or _mapping(raw.get("usage"))
    provider_key = str(provider_id or "").strip().lower().removeprefix("llm:")

    # The normalized row is currently intended for LM Studio. Still accept an
    # explicit stats payload so compatible adapters can opt in without branching.
    if provider_key != "lmstudio" and not stats:
        return metrics

    metrics["provider"] = provider_key or "lmstudio"

    tokens_per_second = _first_number(
        stats.get("tokens_per_second"),
        stats.get("tokensPerSecond"),
    )
    if tokens_per_second is not None:
        metrics["tokens_per_second"] = tokens_per_second

    output_tokens = _first_integer(
        usage.get("completion_tokens"),
        usage.get("output_tokens"),
        stats.get("total_output_tokens"),
        stats.get("predicted_tokens_count"),
    )
    if output_tokens is not None:
        metrics["output_tokens"] = output_tokens

    input_tokens = _first_integer(
        usage.get("prompt_tokens"),
        usage.get("input_tokens"),
        stats.get("input_tokens"),
    )
    if input_tokens is not None:
        metrics["input_tokens"] = input_tokens

    total_tokens = _first_integer(
        usage.get("total_tokens"),
        stats.get("total_tokens"),
    )
    if total_tokens is not None:
        metrics["total_tokens"] = total_tokens

    generation_time = _first_number(
        stats.get("generation_time"),
        stats.get("generation_time_seconds"),
    )
    if generation_time is not None:
        metrics["generation_time_seconds"] = generation_time

    time_to_first_token = _first_number(
        stats.get("time_to_first_token"),
        stats.get("time_to_first_token_seconds"),
    )
    if time_to_first_token is not None:
        metrics["time_to_first_token_seconds"] = time_to_first_token

    stop_reason = _first_text(
        stats.get("stop_reason"),
        getattr(response, "finish_reason", None),
    )
    if stop_reason is not None:
        metrics["stop_reason"] = stop_reason

    finish_reason = _first_text(getattr(response, "finish_reason", None))
    if finish_reason is not None:
        metrics["finish_reason"] = finish_reason

    return metrics
