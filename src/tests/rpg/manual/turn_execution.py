from __future__ import annotations

from typing import Any, Dict

from tests.rpg.manual.safe import _safe_dict, _safe_str
from tests.rpg.manual import output_artifacts


def _run_one_manual_turn(
    *,
    session_id: str,
    turn: Dict[str, Any],
    turn_index: int,
    scenario_name: str,
    target_channel: str,
    console_llm: bool = True,
    console_llm_raw: bool = True,
    console_llm_max_chars: int = 1200,
) -> Dict[str, Any]:
    """Run a single turn for a manual scenario."""
    turn = _safe_dict(turn)
    player_input = _safe_str(
        turn.get("player")
        or turn.get("input")
        or turn.get("player_input")
    )

    if not player_input:
        return {
            "turn_index": turn_index,
            "error": "no_player_input",
            "scenario_warnings": ["no_player_input"],
            "regression_warnings": ["no_player_input"],
        }

    try:
        from app.rpg.session.runtime import apply_turn

        result = apply_turn(session_id=session_id, player_input=player_input)

        # Log to console if requested
        if console_llm:
            _log_llm_response(
                scope="service",
                label=scenario_name,
                turn=turn_index,
                player_input=player_input,
                result=result,
                raw=console_llm_raw,
                max_chars=console_llm_max_chars,
            )

        # Emit to output artifacts
        output_artifacts._emit(f"TURN {turn_index}: {player_input}", channel=target_channel)

        turn_summary = {
            "turn_index": turn_index,
            "player_input": player_input,
            "result": result,
        }

        return turn_summary

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        output_artifacts._emit(f"TURN {turn_index} ERROR: {error_msg}", channel=target_channel)
        return {
            "turn_index": turn_index,
            "player_input": player_input,
            "error": error_msg,
            "scenario_warnings": [f"turn_runtime_error:{error_msg}"],
            "regression_warnings": [f"turn_runtime_error:{error_msg}"],
        }


def _log_llm_response(
    *,
    scope: str,
    label: str,
    turn: int,
    player_input: str,
    result: Dict[str, Any],
    raw: bool = True,
    max_chars: int = 1200,
) -> None:
    """Log LLM response to console for debugging."""
    # Placeholder - need to implement based on old file
    pass