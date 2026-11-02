from __future__ import annotations

from typing import Any, cast

from app.apps.rpg.narration.ai.grounding_settings import normalize_grounding_settings
from app.apps.rpg.world.conversation_settings import normalize_conversation_settings
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict

_ALLOWED_IDLE_SECONDS = (15, 30, 60, 300, 600)
_ALLOWED_REACTION_STYLES = ("minimal", "normal", "lively")
_FAST_TURN_DEFAULTS = {
    "enable_action_advisory": True,
    "enable_semantic_action_advisory": True,
    "enable_live_narration_llm": True,
    "enable_narration_retry": False,
    "enable_fast_live_narrator_mode": True,
    "enable_continuity_grounding": True,
    "compact_save": True,
}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _copy_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    try:
        return bool(value)
    except Exception:
        return default


def npc_profile_settings(settings: dict[str, Any]) -> dict[str, Any]:
    configured = _safe_dict(settings.get("npc_profile_generation"))
    return {
        "auto_create_on_introduction": bool(
            configured.get("auto_create_on_introduction", True)
        ),
        "allow_manual_create": bool(
            configured.get("allow_manual_create", True)
        ),
        "draft_with_llm_on_create": bool(
            configured.get("draft_with_llm_on_create", False)
        ),
    }


def _normalize_final_narration_text(text: str) -> str:
    text = _safe_str(text).strip()
    if not text:
        return ""

    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(_safe_str(raw_line).split()).strip()
        if line:
            normalized_lines.append(line)
        elif normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")

    text = "\n".join(normalized_lines).strip()
    if text and not text.endswith("...") and text[-1] not in ".!?\"'":
        text += "."
    return text


def _normalize_runtime_settings(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    result: dict[str, Any] = {}
    result["mode"] = _safe_str(value.get("mode") or "live").strip().lower() or "live"
    interaction_duration_mode = _safe_str(
        value.get("interaction_duration_mode") or "until_next_command"
    ).strip().lower()
    if interaction_duration_mode not in {"ticks", "until_next_command"}:
        interaction_duration_mode = "ticks"

    interaction_duration_ticks = _safe_int(value.get("interaction_duration_ticks"), 5)
    if interaction_duration_ticks < 1:
        interaction_duration_ticks = 1
    if interaction_duration_ticks > 20:
        interaction_duration_ticks = 20

    result["interaction_duration_mode"] = interaction_duration_mode
    result["interaction_duration_ticks"] = interaction_duration_ticks
    result["interaction_trace"] = _safe_bool(value.get("interaction_trace"), True)
    rl = value.get("response_length")
    if isinstance(rl, str):
        rl_value = rl.strip().lower()
        result["response_length"] = rl_value if rl_value in ("short", "medium", "long") else "short"
    elif isinstance(rl, dict):
        fallback = str(rl.get("narrator_length") or rl.get("character_length") or "").strip().lower()
        result["response_length"] = fallback if fallback in ("short", "medium", "long") else "short"
    else:
        result["response_length"] = "short"
    ics = value.get("idle_conversation_seconds")
    try:
        ics = int(cast(Any, ics))
    except (TypeError, ValueError):
        ics = 15
    result["idle_conversation_seconds"] = ics if ics in _ALLOWED_IDLE_SECONDS else 15
    for bkey in (
        "idle_conversations_enabled",
        "idle_npc_to_player_enabled",
        "idle_npc_to_npc_enabled",
        "follow_reactions_enabled",
        "console_debug_enabled",
        "world_events_panel_enabled",
    ):
        result[bkey] = bool(value.get(bkey, True))
    rs = value.get("reaction_style")
    result["reaction_style"] = (
        rs if isinstance(rs, str) and rs.strip().lower() in _ALLOWED_REACTION_STYLES else "normal"
    )
    result["verbose_semantic_trace"] = _safe_bool(value.get("verbose_semantic_trace"), False)
    # Preserve and normalize nested conversation_settings so UI payloads survive the
    # normalization round-trip without being silently dropped.
    raw_conv = value.get("conversation_settings")
    if isinstance(raw_conv, dict):
        result["conversation_settings"] = normalize_conversation_settings(raw_conv)
    # Preserve npc_profile_generation settings.
    raw_npc_profile_gen = value.get("npc_profile_generation")
    if isinstance(raw_npc_profile_gen, dict):
        result["npc_profile_generation"] = npc_profile_settings(value)

    raw_grounding = value.get("grounding")
    result["grounding"] = normalize_grounding_settings(raw_grounding)

    return result


def _normalize_performance_settings(runtime_state: dict[str, Any]) -> dict[str, Any]:
    perf = {}
    if isinstance(runtime_state, dict):
        perf = dict(runtime_state.get("performance") or {})
    fast = bool(perf.get("fast_turn_mode", False))
    defaults = _FAST_TURN_DEFAULTS if fast else {
        "enable_action_advisory": True,
        "enable_semantic_action_advisory": True,
        "enable_live_narration_llm": True,
        "enable_narration_retry": False,
        "enable_fast_live_narrator_mode": False,
        "enable_continuity_grounding": True,
        "compact_save": False,
    }
    result: dict[str, Any] = {"fast_turn_mode": fast}
    for key, default_val in defaults.items():
        val = perf.get(key)
        result[key] = bool(val) if val is not None else default_val
    result["live_narrator_temperature"] = float(perf.get("live_narrator_temperature", 0.2) or 0.2)
    result["live_narrator_top_p"] = float(perf.get("live_narrator_top_p", 0.9) or 0.9)
    result["continuity_turn_window"] = int(perf.get("continuity_turn_window", 3) or 3)
    return result
