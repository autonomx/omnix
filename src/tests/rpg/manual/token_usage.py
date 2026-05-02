from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.manual.constants import TOKEN_USAGE_PATH
from tests.rpg.manual.extractors.narration_text import (
    _extract_narration,
    _extract_turn_contract,
)
from tests.rpg.manual.output_state import _TOKEN_USAGE_LOCK, _TOKEN_USAGE_ROWS
from tests.rpg.manual.safe import _compact_json, _safe_dict


def _estimate_tokens_from_text(value: Any) -> int:
    text = "" if value is None else str(value)
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def _extract_token_usage_from_any(value: Any) -> Dict[str, Any]:
    value_dict = _safe_dict(value)
    if not value_dict:
        return {}

    usage = _safe_dict(
        value_dict.get("usage")
        or value_dict.get("token_usage")
        or value_dict.get("tokens")
        or value_dict.get("llm_usage")
    )

    if not usage:
        result = _safe_dict(value_dict.get("result"))
        usage = _safe_dict(
            result.get("usage")
            or result.get("token_usage")
            or result.get("tokens")
            or result.get("llm_usage")
        )

    if not usage:
        narration_debug = _safe_dict(_safe_dict(value_dict.get("result")).get("narration_debug"))
        usage = _safe_dict(
            narration_debug.get("usage")
            or narration_debug.get("token_usage")
            or narration_debug.get("tokens")
            or narration_debug.get("llm_usage")
        )

    if not usage:
        return {}

    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt")
        or usage.get("input")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("completion")
        or usage.get("output")
        or 0
    )
    total_tokens = usage.get("total_tokens") or usage.get("total") or 0

    try:
        prompt_tokens = int(prompt_tokens or 0)
    except Exception:
        prompt_tokens = 0
    try:
        completion_tokens = int(completion_tokens or 0)
    except Exception:
        completion_tokens = 0
    try:
        total_tokens = int(total_tokens or 0)
    except Exception:
        total_tokens = 0

    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "source": "provider",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "raw_usage": usage,
    }


def _extract_token_usage_from_result(result: Dict[str, Any], *, player_input: str = "") -> Dict[str, Any]:
    exact = _extract_token_usage_from_any(result)
    if exact:
        return exact

    narration = _extract_narration(result)
    turn_contract = _extract_turn_contract(result)
    result_sub = _safe_dict(result.get("result"))
    narration_debug = _safe_dict(result_sub.get("narration_debug"))
    raw_llm = (
        narration_debug.get("raw_llm_narrative")
        or narration_debug.get("raw_llm_text")
        or result_sub.get("raw_llm_narrative")
        or result_sub.get("raw_llm_text")
        or narration
    )

    estimated_prompt = _estimate_tokens_from_text(player_input) + _estimate_tokens_from_text(turn_contract)
    estimated_completion = _estimate_tokens_from_text(raw_llm or narration)
    return {
        "source": "estimated",
        "prompt_tokens": estimated_prompt,
        "completion_tokens": estimated_completion,
        "total_tokens": estimated_prompt + estimated_completion,
        "raw_usage": {},
    }


def _record_token_usage(
    *,
    scope: str,
    label: str,
    turn: int,
    player_input: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    usage = _extract_token_usage_from_result(result, player_input=player_input)
    row = {
        "scope": scope,
        "label": label,
        "turn": turn,
        "player_input": player_input,
        "source": usage.get("source", ""),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }
    with _TOKEN_USAGE_LOCK:
        _TOKEN_USAGE_ROWS.append(row)
    return row


def _reset_token_usage() -> None:
    with _TOKEN_USAGE_LOCK:
        _TOKEN_USAGE_ROWS.clear()


def _token_usage_totals(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
    }


def write_token_usage_report(path: Path = TOKEN_USAGE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with _TOKEN_USAGE_LOCK:
        rows = list(_TOKEN_USAGE_ROWS)

    by_scope: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_scope.setdefault(str(row.get("scope") or "unknown"), []).append(row)

    lines: List[str] = []
    lines.append("Manual RPG transcript token usage")
    lines.append("=" * 80)
    lines.append("")
    lines.append("NOTE:")
    lines.append("- source=provider means token counts came from provider/runtime usage metadata.")
    lines.append("- source=estimated means counts are rough char/4 estimates from transcript data.")
    lines.append("")

    totals = _token_usage_totals(rows)
    lines.append("TOTALS")
    lines.append("-" * 80)
    lines.append(_compact_json(totals))
    lines.append("")

    lines.append("TOTALS BY SCOPE")
    lines.append("-" * 80)
    for scope in sorted(by_scope):
        lines.append(scope)
        lines.append(_compact_json(_token_usage_totals(by_scope[scope])))
    lines.append("")

    lines.append("ROWS")
    lines.append("-" * 80)
    lines.append(_compact_json(rows))
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote token usage to: {path.resolve()}", flush=True)