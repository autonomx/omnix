"""Runtime hooks for canonical RPG visible-response selection."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any

from app.rpg.session.visible_response_contract import (
    attach_visible_turn_record,
    extract_provider_message_content,
    invalid_visible_selection_reason,
    is_invalid_visible_value,
)

_SENTINEL = "_omnix_visible_response_runtime_guard_installed"
_PARSE_NOISE_VALUES = {"[]", "[ ]", "{}", "{ }", "tool_calls: []", '"tool_calls": []'}


def install_visible_response_runtime_guard() -> None:
    """Install conservative last-mile guards for visible RPG text.

    The hooks are intentionally additive: provider diagnostics stay available,
    but raw metadata such as ``tool_calls: []`` cannot be selected as the player-
    facing turn response.
    """

    try:
        from app.rpg.ai import semantic_action_intelligence as semantic
    except Exception:
        semantic = None
    if semantic is not None and not getattr(semantic, _SENTINEL, False):
        _patch_semantic_provider_extraction(semantic)
        setattr(semantic, _SENTINEL, True)

    try:
        from app.rpg.session import first_call_dialogue
    except Exception:
        first_call_dialogue = None
    if first_call_dialogue is not None and not getattr(first_call_dialogue, _SENTINEL, False):
        _patch_first_call_selection(first_call_dialogue)
        setattr(first_call_dialogue, _SENTINEL, True)

    try:
        from app.rpg.session import interactive_first_call_runtime as runtime
    except Exception:
        runtime = None
    if runtime is not None and not getattr(runtime, _SENTINEL, False):
        _patch_interactive_runtime(runtime)
        setattr(runtime, _SENTINEL, True)

    try:
        from app.rpg.session import response_authority
    except Exception:
        response_authority = None
    if response_authority is not None:
        parse_noise = getattr(response_authority, "_PARSE_NOISE", None)
        if isinstance(parse_noise, set):
            parse_noise.update(_PARSE_NOISE_VALUES)


def _patch_semantic_provider_extraction(semantic: Any) -> None:
    original = semantic._complete_raw_text

    @wraps(original)
    def guarded_complete_raw_text(llm_gateway: Any, prompt: str) -> tuple[Any, str, str]:
        raw_result, raw_text, source = original(llm_gateway, prompt)
        if is_invalid_visible_value(raw_text):
            extracted = extract_provider_message_content(raw_result)
            if extracted:
                return raw_result, extracted, f"{source}:choices_message_content"
        return raw_result, raw_text, source

    semantic._complete_raw_text = guarded_complete_raw_text


def _patch_first_call_selection(first_call_dialogue: Any) -> None:
    original = first_call_dialogue.choose_first_call_visible_response

    @wraps(original)
    def guarded_choose_first_call_visible_response(*args: Any, **kwargs: Any) -> dict[str, Any]:
        selected = original(*args, **kwargs)
        reason = invalid_visible_selection_reason(selected)
        if not reason:
            return selected
        copied = deepcopy(selected) if isinstance(selected, dict) else {}
        source = str(copied.get("source") or "first_call_dialogue_v1")
        return {
            "consumable": False,
            "reason": "no_safe_non_stateful_visible_response",
            "rejection_reasons": [f"{source}:{reason}"],
            "rejected_visible_response": deepcopy(copied.get("visible_response") or {}),
            "source": "visible_response_contract_guard_v1",
        }

    first_call_dialogue.choose_first_call_visible_response = guarded_choose_first_call_visible_response


def _patch_interactive_runtime(runtime: Any) -> None:
    original = runtime.apply_turn

    @wraps(original)
    def guarded_apply_turn(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        player_input = ""
        if len(args) >= 2:
            player_input = str(args[1] or "")
        if not player_input:
            player_input = str(kwargs.get("player_input") or "")
        return attach_visible_turn_record(result, player_input=player_input)

    runtime.apply_turn = guarded_apply_turn
