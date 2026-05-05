from __future__ import annotations

import json
import re
from typing import Any, Dict, List


PROVIDER_METHOD_CANDIDATES = [
    "chat",
    "complete",
    "generate",
    "invoke",
    "generate_response",
    "generate_text",
    "generate_completion",
    "complete_text",
    "ask",
    "prompt",
    "run",
    "call",
    "completion",
    "create_completion",
    "create_chat_completion",
    "chat_completion",
    "send",
    "send_prompt",
    "request",
    "respond",
    "get_response",
    "get_completion",
    "__call__",
]


CHAT_LIKE_PROVIDER_METHODS = {
    "chat",
    "chat_completion",
    "create_chat_completion",
}


PROVIDER_CHILD_CANDIDATES = [
    "client",
    "_client",
    "llm",
    "_llm",
    "model",
    "_model",
    "backend",
    "_backend",
    "provider",
    "_provider",
    "adapter",
    "_adapter",
    "engine",
    "_engine",
    "service",
    "_service",
    "runtime",
    "_runtime",
    "api",
    "_api",
    "connection",
    "_connection",
]


NARRATION_FORMAT_VERSION = "rpg_narration_v2"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


class _ProviderChatMessage:
    """Small adapter for app provider wrappers that expect message.to_dict()."""

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
        }


def is_echo_narration(*, player_action: str, narration: str) -> bool:
    action = _norm(player_action)
    text = _norm(narration)
    return bool(action and text and (text == action or text == action.rstrip(".") or text == action + "."))


def classify_player_action(player_action: str) -> str:
    text = _norm(player_action)
    if any(word in text for word in ["ask", "talk", "tell", "speak", "question", "report", "explain", "share", "approach", "convince", "persuade"]):
        return "social"
    if any(word in text for word in ["look", "inspect", "search", "observe", "scan", "examine", "listen"]):
        return "exploration"
    if any(word in text for word in ["walk", "travel", "leave", "follow", "pursue", "road", "outside"]):
        return "travel"
    if any(word in text for word in ["attack", "strike", "hit", "shoot", "cast", "defend"]):
        return "combat"
    if any(word in text for word in ["buy", "sell", "rent", "room", "drink", "meal", "service"]):
        return "service"
    return "general"


def infer_npc_speaker(player_action: str, simulation_state: Dict[str, Any] | None = None) -> str:
    text = _norm(player_action)
    aliases = {
        "bran": "Bran",
        "innkeeper": "Bran",
        "mira": "Mira",
        "cloaked traveler": "Cloaked Traveler",
        "traveler": "Cloaked Traveler",
        "patron": "Local Patron",
        "guard": "Guard",
        "merchant": "Merchant",
    }
    for key, value in aliases.items():
        if key in text:
            return value

    simulation_state = _safe_dict(simulation_state)
    profiles = _safe_dict(_safe_dict(simulation_state.get("npc_profile_state")).get("profiles"))
    for profile in profiles.values():
        profile = _safe_dict(profile)
        name = _safe_str(profile.get("name"))
        if name and _norm(name) in text:
            return name
    return ""


def _fallback_npc_line(*, speaker: str, player_action: str, action_type: str) -> str:
    text = _norm(player_action)
    if not speaker:
        return ""
    if speaker == "Bran":
        if "bandit" in text or "road" in text:
            return "If the road is involved, then this is bigger than tavern gossip. Be careful how loudly you ask."
        if "witness" in text or "traveler" in text or "found" in text:
            return "Slow down and tell me what you know. Around here, one witness can change the whole story."
        if "room" in text or "rent" in text:
            return "I have rooms, but tonight I am more worried about what followed people here than where they sleep."
        return "Say what you need to say. I am listening, even if the rest of the room is pretending not to."
    if speaker == "Mira":
        return "I notice the things people try to hide. Ask plainly, and I will tell you what I saw."
    if speaker == "Cloaked Traveler":
        return "I did not want to be noticed. That should tell you enough about how dangerous this is."
    if speaker == "Local Patron":
        return "People saw more than they are admitting. Fear has a way of keeping mugs close and mouths shut."
    return "The reply comes cautiously, shaped by the pressure in the room."


def build_deterministic_narration_payload(
    *,
    player_action: str,
    simulation_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a safe presentation-only narration payload.

    This is a fallback, not a simulation authority. It describes only that the
    moment responds to the player's action. It does not award, complete, mutate,
    or invent authoritative facts.
    """
    simulation_state = _safe_dict(simulation_state)
    turn_contract = _safe_dict(turn_contract)
    action_type = classify_player_action(player_action)
    speaker = infer_npc_speaker(player_action, simulation_state)

    if action_type == "social":
        speaker = speaker or "Local Patron"
        narration = f"{speaker} reacts to the question, and the surrounding noise seems to thin as the conversation draws attention."
        npc_line = _fallback_npc_line(speaker=speaker, player_action=player_action, action_type=action_type)
    elif action_type == "exploration":
        narration = "The search draws out grounded details from the scene: small marks, watchful faces, and signs of recent tension."
        npc_line = ""
    elif action_type == "travel":
        narration = "The scene shifts with the movement, carrying the pressure of the current lead into the space ahead."
        npc_line = ""
    elif action_type == "combat":
        narration = "The hostile motion sharpens the moment, but the actual outcome remains bound to the combat result."
        npc_line = ""
    elif action_type == "service":
        speaker = speaker or "Bran"
        narration = "The practical request lands against the unease of the room, making ordinary business feel less ordinary."
        npc_line = _fallback_npc_line(speaker=speaker, player_action=player_action, action_type=action_type)
    else:
        narration = "The moment responds without producing a major new consequence."
        npc_line = ""

    if is_echo_narration(player_action=player_action, narration=narration):
        narration = "The scene responds with a grounded beat rather than merely repeating the attempted action."

    return {
        "format_version": NARRATION_FORMAT_VERSION,
        "narration": narration,
        "action": _safe_str(turn_contract.get("summary") or turn_contract.get("action") or "The action is acknowledged by the scene."),
        "npc": {
            "speaker": speaker if npc_line else "",
            "line": npc_line,
        },
        "reward": "",
        "followup_hooks": [],
        "source": "deterministic_runtime_narration_fallback",
        "authoritative_changes": False,
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _call_provider_text(provider: Any, prompt: str, *, max_tokens: int = 320) -> str:
    if provider is None:
        return ""
    for method_name in ("chat", "complete", "generate", "invoke"):
        method = getattr(provider, method_name, None)
        if not callable(method):
            continue
        try:
            if method_name == "chat":
                response = method(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are the presentation-only narration layer for a deterministic RPG. "
                                "Return JSON only."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                )
            else:
                response = method(prompt, max_tokens=max_tokens)
            if isinstance(response, str):
                return response
            if isinstance(response, dict):
                return _safe_str(response.get("content") or response.get("text") or response.get("response"))
            content = getattr(response, "content", "")
            if content:
                return str(content)
        except Exception:
            continue
    return ""


def _provider_shape(provider: Any) -> Dict[str, Any]:
    if provider is None:
        return {"present": False}
    candidates = []
    for candidate in _provider_candidates(provider):
        obj = candidate["object"]
        candidates.append(
            {
                "path": candidate["path"],
                "type": type(obj).__name__,
                "candidate_methods": [
                    name
                    for name in PROVIDER_METHOD_CANDIDATES
                    if callable(getattr(obj, name, None))
                ],
                "public_callables": _public_callable_names(obj),
            }
        )
    return {
        "present": True,
        "type": type(provider).__name__,
        "callable_methods": [
            name
            for name in PROVIDER_METHOD_CANDIDATES
            if callable(getattr(provider, name, None))
        ],
        "candidate_objects": candidates,
        "has_chat": callable(getattr(provider, "chat", None)),
        "has_complete": callable(getattr(provider, "complete", None)),
        "has_generate": callable(getattr(provider, "generate", None)),
        "has_invoke": callable(getattr(provider, "invoke", None)),
        "has_generate_response": callable(getattr(provider, "generate_response", None)),
        "has_generate_text": callable(getattr(provider, "generate_text", None)),
        "has_ask": callable(getattr(provider, "ask", None)),
        "has_call": callable(getattr(provider, "__call__", None)),
    }


def _extract_provider_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        for key in ("content", "text", "response", "output", "message"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                nested = _extract_provider_text(value)
                if nested:
                    return nested
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            nested = _extract_provider_text(choices[0])
            if nested:
                return nested
        return ""
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        nested = _extract_provider_text(choices[0])
        if nested:
            return nested
    message = getattr(response, "message", None)
    if message is not None:
        nested = _extract_provider_text(message)
        if nested:
            return nested
    delta = getattr(response, "delta", None)
    if delta is not None:
        nested = _extract_provider_text(delta)
        if nested:
            return nested
    for attr in ("content", "text", "response", "output"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            nested = _extract_provider_text(value)
            if nested:
                return nested
    return ""


def _public_callable_names(value: Any, *, limit: int = 80) -> List[str]:
    if value is None:
        return []
    names: List[str] = []
    try:
        for name in dir(value):
            if name.startswith("__") and name != "__call__":
                continue
            if name.startswith("_") and name not in {"_client", "_provider", "_backend", "_model", "_llm"}:
                continue
            try:
                attr = getattr(value, name)
            except Exception:
                continue
            if callable(attr):
                names.append(name)
            if len(names) >= limit:
                break
    except Exception:
        return names
    return sorted(set(names))


def _safe_child_objects(provider: Any) -> List[Dict[str, Any]]:
    children: List[Dict[str, Any]] = []
    if provider is None:
        return children
    seen = {id(provider)}
    for attr_name in PROVIDER_CHILD_CANDIDATES:
        try:
            child = getattr(provider, attr_name, None)
        except Exception:
            continue
        if child is None:
            continue
        if id(child) in seen:
            continue
        if isinstance(child, (str, int, float, bool, list, tuple, dict, set)):
            continue
        seen.add(id(child))
        children.append(
            {
                "path": attr_name,
                "object": child,
            }
        )
    return children


def _provider_candidates(provider: Any) -> List[Dict[str, Any]]:
    candidates = [{"path": "root", "object": provider}]
    candidates.extend(_safe_child_objects(provider))
    return candidates


def _try_provider_call(method: Any, method_name: str, prompt: str, *, max_tokens: int) -> Any:
    dict_messages = [
        {
            "role": "system",
            "content": (
                "You are the presentation-only narration layer for a deterministic RPG. "
                "Return JSON only."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    object_messages = [
        _ProviderChatMessage(
            "system",
            "You are the presentation-only narration layer for a deterministic RPG. Return JSON only.",
        ),
        _ProviderChatMessage("user", prompt),
    ]

    attempts = []
    if method_name in CHAT_LIKE_PROVIDER_METHODS:
        attempts.extend(
            [
                lambda: method(object_messages, max_tokens=max_tokens),
                lambda: method(messages=object_messages, max_tokens=max_tokens),
                lambda: method(object_messages),
                lambda: method(dict_messages, max_tokens=max_tokens),
                lambda: method(messages=dict_messages, max_tokens=max_tokens),
                lambda: method(dict_messages),
            ]
        )
    else:
        attempts.extend(
            [
                lambda: method(prompt, max_tokens=max_tokens),
                lambda: method(prompt=prompt, max_tokens=max_tokens),
                lambda: method(text=prompt, max_tokens=max_tokens),
                lambda: method(message=prompt, max_tokens=max_tokens),
                lambda: method(user_message=prompt, max_tokens=max_tokens),
                lambda: method(input=prompt, max_tokens=max_tokens),
                lambda: method(messages=object_messages, max_tokens=max_tokens),
                lambda: method(messages=dict_messages, max_tokens=max_tokens),
                lambda: method(prompt),
                lambda: method(prompt=prompt),
                lambda: method(text=prompt),
                lambda: method(message=prompt),
                lambda: method(user_message=prompt),
                lambda: method(input=prompt),
                lambda: method(messages=object_messages),
                lambda: method(messages=dict_messages),
            ]
        )

    last_error = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return None


def _call_provider_text_with_diagnostics(
    provider: Any,
    prompt: str,
    *,
    max_tokens: int = 320,
) -> Dict[str, Any]:
    diagnostics = {
        "provider_shape": _provider_shape(provider),
        "attempted_methods": [],
        "method_errors": {},
        "selected_method": "",
        "raw_text_length": 0,
        "raw_text_excerpt": "",
        "error": "",
    }
    if provider is None:
        diagnostics["error"] = "provider_not_available"
        return {"text": "", "diagnostics": diagnostics}

    any_supported = False
    for candidate in _provider_candidates(provider):
        candidate_path = str(candidate.get("path") or "root")
        candidate_obj = candidate.get("object")
        callable_methods = [
            name
            for name in PROVIDER_METHOD_CANDIDATES
            if callable(getattr(candidate_obj, name, None))
        ]
        if not callable_methods:
            continue
        any_supported = True
        for method_name in callable_methods:
            method = getattr(candidate_obj, method_name)
            attempt_name = f"{candidate_path}.{method_name}"
            diagnostics["attempted_methods"].append(attempt_name)
            try:
                response = _try_provider_call(
                    method,
                    method_name,
                    prompt,
                    max_tokens=max_tokens,
                )
                text = _extract_provider_text(response)
                diagnostics["raw_text_length"] = len(text)
                diagnostics["raw_text_excerpt"] = text[:500]
                if text.strip():
                    diagnostics["selected_method"] = attempt_name
                    return {"text": text, "diagnostics": diagnostics}
                diagnostics["method_errors"][attempt_name] = "provider_returned_empty_text"
            except Exception as exc:
                diagnostics["method_errors"][attempt_name] = f"{type(exc).__name__}: {exc}"

    if not any_supported:
        diagnostics["error"] = "provider_has_no_supported_call_method"
        return {"text": "", "diagnostics": diagnostics}

    if diagnostics["method_errors"]:
        diagnostics["error"] = "provider_call_failed"
    else:
        diagnostics["error"] = "provider_returned_empty_text"
    return {"text": "", "diagnostics": diagnostics}


def validate_narration_payload(
    payload: Dict[str, Any],
    *,
    player_action: str,
) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    errors: List[str] = []

    if payload.get("format_version") != NARRATION_FORMAT_VERSION:
        errors.append("invalid_format_version")
    narration = _safe_str(payload.get("narration"))
    if not narration:
        errors.append("missing_narration")
    if is_echo_narration(player_action=player_action, narration=narration):
        errors.append("echoed_player_action")
    npc = _safe_dict(payload.get("npc"))
    if not isinstance(payload.get("npc"), dict):
        errors.append("npc_not_object")
    if payload.get("reward") not in ("", None):
        errors.append("reward_not_empty")
    hooks = payload.get("followup_hooks")
    if hooks not in ([], None):
        errors.append("followup_hooks_not_empty")
    if payload.get("authoritative_changes") not in (False, None):
        errors.append("authoritative_changes_not_false")

    normalized = {
        "format_version": NARRATION_FORMAT_VERSION,
        "narration": narration,
        "action": _safe_str(payload.get("action")),
        "npc": {
            "speaker": _safe_str(npc.get("speaker")),
            "line": _safe_str(npc.get("line")),
        },
        "reward": "",
        "followup_hooks": [],
        "source": _safe_str(payload.get("source") or "runtime_narration"),
        "authoritative_changes": False,
    }
    return {
        "ok": not errors,
        "errors": errors,
        "payload": normalized,
    }


def _safe_action_acknowledgement(turn_contract: Dict[str, Any] | None = None) -> str:
    turn_contract = _safe_dict(turn_contract)
    return _safe_str(
        turn_contract.get("summary")
        or turn_contract.get("result")
        or turn_contract.get("action_result")
        or turn_contract.get("action")
        or "The scene acknowledges the attempted action without changing any authoritative state."
    )


def _provider_action_looks_authoritative(action: str) -> bool:
    text = _norm(action)
    suspicious = [
        "roll:",
        "dc:",
        "succeeded",
        "failed",
        "critical",
        "damage",
        "xp",
        "gold",
        "item",
        "reward",
        "quest complete",
        "objective complete",
        "level up",
    ]
    return any(token in text for token in suspicious)


def repair_provider_narration_payload(
    payload: Dict[str, Any],
    *,
    player_action: str,
    turn_contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Repair provider JSON into the presentation-only narration contract.

    Repair is intentionally conservative:
    - never preserves reward
    - never preserves followup_hooks
    - never preserves authoritative_changes
    - replaces authoritative-looking action text
    """
    payload = _safe_dict(payload)
    repaired = dict(payload)
    repair_actions: List[str] = []

    repaired["format_version"] = NARRATION_FORMAT_VERSION

    if repaired.get("reward") not in ("", None):
        repair_actions.append("cleared_reward")
    repaired["reward"] = ""

    if repaired.get("followup_hooks") not in ([], None):
        repair_actions.append("cleared_followup_hooks")
    repaired["followup_hooks"] = []

    if repaired.get("authoritative_changes") not in (False, None):
        repair_actions.append("cleared_authoritative_changes")
    repaired["authoritative_changes"] = False

    action = _safe_str(repaired.get("action"))
    if not action or _provider_action_looks_authoritative(action):
        repaired["action"] = _safe_action_acknowledgement(turn_contract)
        repair_actions.append("replaced_action")

    npc = _safe_dict(repaired.get("npc"))
    repaired["npc"] = {
        "speaker": _safe_str(npc.get("speaker")),
        "line": _safe_str(npc.get("line")),
    }

    repaired["source"] = "provider_runtime_narration"
    repaired["_repair_actions"] = repair_actions
    return repaired


def build_provider_narration_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any] | None = None,
    max_tokens: int = 320,
    repair_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    turn_contract = _safe_dict(turn_contract)
    action_type = classify_player_action(player_action)
    target_npc = infer_npc_speaker(player_action, simulation_state)

    prompt = {
        "task": "Produce structured RPG narration for a completed deterministic turn.",
        "schema": {
            "format_version": NARRATION_FORMAT_VERSION,
            "narration": "2-5 sentences describing how the scene responds. Do not repeat the player input.",
            "action": "Result/acknowledgement of the action, not the original action text.",
            "npc": {"speaker": "NPC name or empty", "line": "NPC line or empty"},
            "reward": "",
            "followup_hooks": [],
        },
        "rules": [
            "Simulation is authoritative. You cannot award XP, gold, items, damage, quest completion, or story outcomes.",
            "Do not invent rewards.",
            "Do not mutate state.",
            "Do not say 'the player'.",
            "Do not repeat the player input.",
            "If the action addresses an NPC, include a grounded npc.speaker and npc.line.",
            "reward MUST be an empty string.",
            "followup_hooks MUST be an empty array.",
            "authoritative_changes MUST be false if included.",
            "Do not include rolls, DCs, success/failure claims, XP, gold, item changes, quest completion, or objective completion unless already present in the deterministic turn_contract.",
            "Return JSON only.",
        ],
        "previous_attempt_repair_context": _safe_dict(repair_context),
        "player_action": player_action,
        "action_type": action_type,
        "target_npc": target_npc,
        "turn_contract": turn_contract,
        "bounded_state_summary": {
            "scene": simulation_state.get("scene"),
            "location": simulation_state.get("location"),
            "story_arc_state": simulation_state.get("story_arc_state"),
            "campaign_journal_state": simulation_state.get("campaign_journal_state"),
            "npc_profile_state": simulation_state.get("npc_profile_state"),
        },
    }
    call_result = _call_provider_text_with_diagnostics(
        provider,
        json.dumps(prompt, ensure_ascii=False),
        max_tokens=max_tokens,
    )
    raw = _safe_str(call_result.get("text"))
    call_diagnostics = _safe_dict(call_result.get("diagnostics"))
    parsed = _extract_json_object(raw)
    if parsed:
        parsed["source"] = "provider_runtime_narration"
    parsed["_raw_provider_response"] = raw
    parsed["_provider_call_diagnostics"] = call_diagnostics
    return parsed


def build_runtime_narration_payload(
    *,
    provider: Any = None,
    player_action: str,
    simulation_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any] | None = None,
    prefer_provider: bool = True,
    max_tokens: int = 320,
    max_provider_attempts: int = 2,
) -> Dict[str, Any]:
    diagnostics = {
        "provider_requested": bool(prefer_provider),
        "provider_present": provider is not None,
        "provider_shape": _provider_shape(provider),
        "provider_attempted": False,
        "provider_valid": False,
        "provider_errors": [],
        "provider_call_diagnostics": {},
        "provider_repaired": False,
        "provider_repair_actions": [],
        "provider_original_errors": [],
        "fallback_used": False,
    }
    if prefer_provider and provider is not None:
        diagnostics["provider_attempt_count"] = 0
        diagnostics["provider_retry_count"] = 0
        diagnostics["provider_attempt_errors"] = []
        last_provider_payload: Dict[str, Any] = {}
        last_validated: Dict[str, Any] = {}
        repair_context: Dict[str, Any] = {}

        for attempt_index in range(max(1, int(max_provider_attempts))):
            diagnostics["provider_attempt_count"] += 1
            provider_payload = build_provider_narration_payload(
                provider=provider,
                player_action=player_action,
                simulation_state=simulation_state,
                turn_contract=turn_contract,
                max_tokens=max_tokens,
                repair_context=repair_context,
            )
            last_provider_payload = provider_payload
            diagnostics["provider_call_diagnostics"] = _safe_dict(
                provider_payload.get("_provider_call_diagnostics")
            )
            validated = validate_narration_payload(provider_payload, player_action=player_action)
            last_validated = validated
            if validated["ok"]:
                diagnostics["provider_valid"] = True
                diagnostics["provider_repaired"] = False
                payload = validated["payload"]
                payload["raw_provider_response"] = _safe_str(provider_payload.get("_raw_provider_response"))
                payload["runtime_narration_diagnostics"] = diagnostics
                return payload

            errors = list(validated.get("errors") or [])
            diagnostics["provider_attempt_errors"].append(
                {
                    "attempt": attempt_index + 1,
                    "errors": errors,
                }
            )
            call_diag = _safe_dict(provider_payload.get("_provider_call_diagnostics"))
            if call_diag.get("error") or not _safe_str(provider_payload.get("_raw_provider_response")):
                break
            if attempt_index + 1 < max(1, int(max_provider_attempts)):
                diagnostics["provider_retry_count"] += 1
                repair_context = {
                    "previous_errors": errors,
                    "instruction": (
                        "Retry with valid JSON only. reward must be ''. followup_hooks must be []. "
                        "Do not include rolls, DCs, rewards, XP, item changes, or objective completion."
                    ),
                }

        repaired_provider_payload = repair_provider_narration_payload(
            last_provider_payload,
            player_action=player_action,
            turn_contract=turn_contract,
        )
        repaired_validated = validate_narration_payload(
            repaired_provider_payload,
            player_action=player_action,
        )
        if repaired_validated["ok"]:
            diagnostics["provider_valid"] = True
            diagnostics["provider_repaired"] = True
            diagnostics["provider_repair_actions"] = list(
                repaired_provider_payload.get("_repair_actions") or []
            )
            diagnostics["provider_original_errors"] = list(last_validated.get("errors") or [])
            payload = repaired_validated["payload"]
            payload["raw_provider_response"] = _safe_str(last_provider_payload.get("_raw_provider_response"))
            payload["runtime_narration_diagnostics"] = diagnostics
            return payload
        call_diag = _safe_dict(last_provider_payload.get("_provider_call_diagnostics"))
        if call_diag.get("error"):
            diagnostics["provider_errors"] = [str(call_diag.get("error"))]
        elif not _safe_str(last_provider_payload.get("_raw_provider_response")):
            diagnostics["provider_errors"] = ["provider_returned_empty_text"]
        else:
            diagnostics["provider_errors"] = list(last_validated.get("errors") or [])
    elif prefer_provider and provider is None:
        diagnostics["provider_errors"] = ["provider_not_available"]

    fallback = build_deterministic_narration_payload(
        player_action=player_action,
        simulation_state=simulation_state,
        turn_contract=turn_contract,
    )
    payload = validate_narration_payload(fallback, player_action=player_action)["payload"]
    diagnostics["fallback_used"] = True
    payload["runtime_narration_diagnostics"] = diagnostics
    return payload