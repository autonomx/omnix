"""Apply deterministic NPC-dialogue quality policy at the turn boundary."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from app.rpg.presentation.dialogue_quality import (
    dialogue_quality_contract_text,
    enforce_dialogue_quality,
)

_RUNTIME_SENTINEL = "_omnix_dialogue_quality_hook_installed"
_PROMPT_SENTINEL = "_omnix_dialogue_quality_prompt_installed"


def install_dialogue_quality_hook() -> None:
    _install_prompt_contract()

    from app.rpg.session import interactive_first_call_runtime

    if getattr(interactive_first_call_runtime, _RUNTIME_SENTINEL, False):
        return
    original_apply_turn: Callable[..., dict[str, Any]] = interactive_first_call_runtime.apply_turn

    @wraps(original_apply_turn)
    def apply_turn_with_dialogue_quality(
        session_id: str,
        player_input: str,
        action: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = original_apply_turn(session_id, player_input, action, *args, **kwargs)
        if not isinstance(result, dict) or result.get("ok") is not True:
            return result
        session = result.get("session")
        session_override = kwargs.get("session_override")
        if not isinstance(session, dict) and isinstance(session_override, dict):
            session = session_override
        if not isinstance(session, dict):
            try:
                from .service import load_session

                session = load_session(session_id)
            except Exception:
                session = {}
        enforced = enforce_dialogue_quality(
            result,
            session=session if isinstance(session, dict) else {},
            player_input=player_input,
        )
        enforced["dialogue_quality_hook_applied"] = True
        return enforced

    interactive_first_call_runtime.apply_turn = apply_turn_with_dialogue_quality
    setattr(interactive_first_call_runtime, _RUNTIME_SENTINEL, True)


def _install_prompt_contract() -> None:
    from app.rpg.ai import semantic_action_intelligence

    if getattr(semantic_action_intelligence, _PROMPT_SENTINEL, False):
        return
    original: Callable[..., str] = semantic_action_intelligence.build_semantic_action_prompt

    @wraps(original)
    def build_prompt_with_dialogue_quality(*args: Any, **kwargs: Any) -> str:
        prompt = original(*args, **kwargs)
        return f"{prompt}\nDIALOGUE_QUALITY_CONTRACT:\n{dialogue_quality_contract_text()}"

    semantic_action_intelligence.build_semantic_action_prompt = build_prompt_with_dialogue_quality
    setattr(semantic_action_intelligence, _PROMPT_SENTINEL, True)
