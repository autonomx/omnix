"""World-grounded interpretive adjudication for meaningful non-mechanical RPG input.

This layer sits between first-call safe dialogue and hard deterministic runtime.
It is intentionally non-mutating: it may explain, refuse, doubt, or contextualize
an unsupported/implausible prompt in-world, but it must not change inventory,
currency, quest, combat, travel, or relationship state.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_INTERPRETIVE_SOURCE = "world_grounded_interpretive_adjudication_v1"
_GENERIC_PARSE_FAILURE_REASONS = {
    "missing_visible_response_text",
    "no_safe_non_stateful_visible_response",
}
_HARD_MECHANIC_TERMS = (
    " buy ",
    " sell ",
    " attack ",
    " hit ",
    " stab ",
    " shoot ",
    " cast ",
    " equip ",
    " unequip ",
    " travel ",
    " go to ",
    " take ",
    " steal ",
    " pay ",
    " hire ",
    " join me",
)
_CLIENT_CORRUPTION_MARKERS = ("[object object]", "undefined", "null")


def classify_interpretive_intent(
    *,
    player_input: str,
    semantic_advisory: dict[str, Any] | None = None,
    selection: dict[str, Any] | None = None,
) -> str:
    """Return a non-mutating interpretive intent category, or an empty string.

    This deliberately favors false negatives over swallowing supported mechanics.
    PRs that add richer intent classes can expand this map without changing the
    runtime boundary: interpreted responses remain non-stateful.
    """

    text = _norm_words(player_input)
    if not _looks_like_meaningful_player_input(text):
        return ""

    selection = _d(selection)
    if selection.get("consumable"):
        return ""
    if selection.get("reason") == "service_or_commerce_runtime_wins":
        return ""

    compact = f" {text} "
    if any(term in compact for term in _HARD_MECHANIC_TERMS):
        return ""

    if re.search(r"\blook(s|ed|ing)? around\b", text) or text in {"look", "look around"}:
        return "observation_request"
    if re.search(r"\bask\b.+\bto\b", text):
        return "npc_capability_request"
    if re.search(r"\bowe[sd]? me\b", text) or re.search(r"\byou owe\b", text):
        return "unverified_debt_claim"
    if re.search(r"\bi (tell|claim|say|said|used to|was|am)\b", text):
        return "unverified_player_claim"
    if re.search(r"\bdo you trust me\b|\btrust me\b|\bwhat do you think of me\b", text):
        return "social_probe"

    advisory = _d(semantic_advisory)
    action_type = _s(advisory.get("action_type")).lower()
    family = _s(advisory.get("semantic_family")).lower()
    mode = _s(advisory.get("interaction_mode")).lower()
    target = _s(advisory.get("target_id") or advisory.get("target_name"))
    reason = _s(selection.get("reason"))
    if (
        reason in _GENERIC_PARSE_FAILURE_REASONS
        and (mode == "direct" or family == "social" or action_type == "social_activity" or target.startswith("npc:"))
    ):
        return "unsupported_but_diegetic_action"
    return ""


def should_use_interpretive_adjudication(
    *,
    player_input: str,
    semantic_advisory: dict[str, Any] | None = None,
    selection: dict[str, Any] | None = None,
    service_matched: bool = False,
) -> bool:
    if service_matched:
        return False
    return bool(
        classify_interpretive_intent(
            player_input=player_input,
            semantic_advisory=_d(semantic_advisory),
            selection=_d(selection),
        )
    )


def build_interpretive_adjudication_result(
    *,
    session: dict[str, Any],
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
    player_input: str,
    action_advisory: dict[str, Any] | None = None,
    semantic_advisory: dict[str, Any] | None = None,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a non-stateful, diegetic answer for meaningful unsupported input."""

    action_advisory = _d(action_advisory)
    semantic_advisory = _d(semantic_advisory)
    selection = _d(selection)
    diagnostics = _first_call_diagnostics(action_advisory, semantic_advisory)
    packet = _d(diagnostics.get("turn_grounding_packet"))
    profile = _addressed_profile(packet)
    speaker = _speaker_name(profile, semantic_advisory)
    intent = classify_interpretive_intent(
        player_input=player_input,
        semantic_advisory=semantic_advisory,
        selection=selection,
    ) or "unsupported_but_diegetic_action"
    line = _line_for_intent(intent=intent, speaker=speaker, profile=profile, player_input=player_input)
    narration = _narration_for_intent(intent=intent, speaker=speaker, player_input=player_input)
    visible_response = {"narration": narration, "npc": {"speaker": speaker, "line": line}}
    grounding_validation = {
        "ok": True,
        "selected_candidate": "interpretive_adjudication",
        "interpretive_intent": intent,
        "fallback_used": True,
        "fallback_source": _INTERPRETIVE_SOURCE,
        "violations": [],
        "primary_violations": [],
        "state_mutation_allowed": False,
        "state_mutation_applied": False,
        "first_call_grounding_packet_version": _s(packet.get("format_version")),
        "first_call_addressed_npc_ids": _l(_d(packet.get("priority_context")).get("addressed_npc_ids")),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "turn_grounding_packet": deepcopy(packet),
        "source": _INTERPRETIVE_SOURCE,
    }
    resolved_result = {
        "ok": True,
        "action_type": "interpretive_adjudication",
        "semantic_action_type": "interpretive_adjudication",
        "semantic_family": "social",
        "interpretive_intent": intent,
        "stateful": False,
        "needs_runtime_resolution": False,
        "no_state_mutation": True,
        "visible_interaction_reason": "world_grounded_interpretive_adjudication",
        "outcome": "interpretive_adjudication",
        "summary": narration,
        "npc": deepcopy(visible_response["npc"]),
        "visible_response": deepcopy(visible_response),
        "first_call_visible_response_selection": deepcopy(selection),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "grounding_validation": deepcopy(grounding_validation),
        "source": _INTERPRETIVE_SOURCE,
    }
    return {
        "consumed": True,
        "ok": True,
        "result": deepcopy(resolved_result),
        "resolved_result": deepcopy(resolved_result),
        "narration": narration,
        "final_narration": narration,
        "summary": narration,
        "npc": deepcopy(visible_response["npc"]),
        "visible_response": deepcopy(visible_response),
        "first_call_visible_response_selection": deepcopy(selection),
        "first_call_action_advisory": deepcopy(action_advisory),
        "first_call_semantic_advisory": deepcopy(semantic_advisory),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "grounding_validation": deepcopy(grounding_validation),
        "llm_called": True,
        "llm_purpose": "world_grounded_interpretive_adjudication",
        "stateful": False,
        "needs_runtime_resolution": False,
        "no_state_mutation": True,
        "simulation_state": deepcopy(_d(simulation_state)),
        "runtime_state": deepcopy(_d(runtime_state)),
        "session": deepcopy(_d(session)),
        "player_input": _s(player_input),
        "source": _INTERPRETIVE_SOURCE,
    }


def install_interpretive_adjudication_hook() -> None:
    """Install the adjudication path into the current interactive runtime.

    The project already uses optional runtime hooks for narrow, auditable slices.
    This hook only diverts meaningful unsupported input before deterministic
    runtime fallback; supported service/commerce/mechanic turns still win.
    """

    from functools import wraps

    from app.rpg.session import interactive_first_call_runtime as runtime

    sentinel = "_omnix_interpretive_adjudication_hook_installed"
    if getattr(runtime, sentinel, False):
        return

    original_should = runtime._should_safe_fallback_nonstateful_dialogue
    original_result = runtime._safe_dialogue_fallback_result

    @wraps(original_should)
    def patched_should(*args: Any, **kwargs: Any) -> bool:
        if original_should(*args, **kwargs):
            return True
        action_advisory = _d(args[0] if len(args) > 0 else kwargs.get("action_advisory"))
        semantic_advisory = _d(args[1] if len(args) > 1 else kwargs.get("semantic_advisory"))
        selection = _d(args[2] if len(args) > 2 else kwargs.get("selection"))
        player_input = _s(kwargs.get("player_input"))
        return should_use_interpretive_adjudication(
            player_input=player_input,
            semantic_advisory=semantic_advisory or action_advisory,
            selection=selection,
        )

    @wraps(original_result)
    def patched_result(**kwargs: Any) -> dict[str, Any]:
        player_input = _s(kwargs.get("player_input"))
        semantic_advisory = _d(kwargs.get("semantic_advisory"))
        selection = _d(kwargs.get("selection"))
        if should_use_interpretive_adjudication(
            player_input=player_input,
            semantic_advisory=semantic_advisory,
            selection=selection,
        ):
            return build_interpretive_adjudication_result(**kwargs)
        return original_result(**kwargs)

    runtime._should_safe_fallback_nonstateful_dialogue = patched_should
    runtime._safe_dialogue_fallback_result = patched_result
    setattr(runtime, sentinel, True)


def _first_call_diagnostics(action_advisory: dict[str, Any], semantic_advisory: dict[str, Any]) -> dict[str, Any]:
    return _d(
        _d(semantic_advisory).get("first_call_grounding_diagnostics")
        or _d(action_advisory).get("first_call_grounding_diagnostics")
    )


def _addressed_profile(packet: dict[str, Any]) -> dict[str, Any]:
    addressed = _l(_d(packet.get("npc_context")).get("addressed_npcs"))
    return _d(addressed[0]) if addressed else {}


def _speaker_name(profile: dict[str, Any], semantic_advisory: dict[str, Any]) -> str:
    return _s(profile.get("name") or semantic_advisory.get("target_name") or "NPC").strip() or "NPC"


def _line_for_intent(*, intent: str, speaker: str, profile: dict[str, Any], player_input: str) -> str:
    role = _s(profile.get("role") or profile.get("occupation") or profile.get("title")).strip()
    role_phrase = f" as {role}" if role else ""
    if intent == "npc_capability_request":
        return (
            f"{_first_person(speaker)} considers the request{role_phrase}, then answers from what is plausible here: "
            "that is not something I can honestly promise or perform just because you asked. "
            "If you mean something practical, say what outcome you want."
        )
    if intent == "unverified_debt_claim":
        return (
            "I do not accept debts just because someone names a number. "
            "Show proof, a witness, or a ledger entry, and I will answer that. Until then, that claim stays unproven."
        )
    if intent == "unverified_player_claim":
        return (
            "That may be a story, a boast, or the truth, but I cannot treat it as fact without proof. "
            "I will judge what you do here and now before I rewrite the past around your words."
        )
    if intent == "social_probe":
        return (
            "Trust is not granted by a question. "
            "I can answer you honestly, but I will weigh your words against what I have seen you do."
        )
    if intent == "observation_request":
        return (
            "Look with your own eyes first: the place, the people, and the mood all matter. "
            "Name what you want to inspect, and I will answer from what can be seen or known here."
        )
    return (
        "I can respond to that in-world, but I will not turn an unsupported request into a fact. "
        "Say what you want to accomplish, and I will answer from what is possible here."
    )


def _narration_for_intent(*, intent: str, speaker: str, player_input: str) -> str:
    if intent == "npc_capability_request":
        return f"{speaker} measures the request against the limits of the moment."
    if intent == "unverified_debt_claim":
        return f"{speaker} treats the claimed debt as something that needs proof."
    if intent == "unverified_player_claim":
        return f"{speaker} weighs your claim without accepting it as proven fact."
    if intent == "social_probe":
        return f"{speaker} answers cautiously, judging trust by evidence rather than words."
    return f"{speaker} keeps the answer grounded in what can be known here."


def _first_person(speaker: str) -> str:
    return "I"


def _looks_like_meaningful_player_input(text: str) -> bool:
    if not text or text in _CLIENT_CORRUPTION_MARKERS:
        return False
    if len(text) < 3:
        return False
    words = text.split()
    if len(words) <= 1 and len(text) < 8:
        return False
    alpha = sum(1 for char in text if char.isalpha())
    return alpha >= max(3, len(text) // 3)


def _norm_words(value: Any) -> str:
    return re.sub(r"[^a-z0-9']+", " ", _s(value).casefold()).strip()


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return str(value) if value is not None else ""
