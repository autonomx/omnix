"""Deterministic quality policy and repair for direct NPC dialogue."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .visible_response import build_visible_response

DIALOGUE_QUALITY_VERSION = "rpg_dialogue_quality_v1"
TARGET_MIN_WORDS = 45
TARGET_MAX_WORDS = 110
_HARD_MIN_LINE_WORDS = 14
_HARD_MAX_TOTAL_WORDS = 150
_GENERIC_PHRASES = (
    "answers carefully",
    "tired but genuine smile",
    "ask that plainly again",
    "as best i can",
    "looks up from the counter",
    "looks up from his work",
)


def dialogue_quality_contract_text() -> str:
    return (
        "For safe non-stateful direct NPC dialogue, return one compact scene action and an NPC line. "
        "Aim for 45-110 words total. Directly answer the player's question, use one specific public scene/profile detail, "
        "keep the NPC's established speech style, and use recent dialogue to avoid repeating the same answer. "
        "An optional conversational or story hook is encouraged. Never reveal private biography, private inventory, "
        "hidden faction knowledge, or invent prices, inventory changes, rewards, quest progress, or other hard-state changes. "
        "Do not merely restate the player's input and do not use generic filler such as 'answers carefully'."
    )


def enforce_dialogue_quality(
    result: dict[str, Any],
    *,
    session: dict[str, Any] | None,
    player_input: str,
) -> dict[str, Any]:
    """Validate safe direct dialogue and deterministically repair weak output."""

    if not _is_nonstateful_direct_dialogue(result):
        return result
    session = session if isinstance(session, dict) else {}
    visible = build_visible_response(result, player_input)
    profile = _addressed_profile(result, session, visible)
    recent = _recent_interactions(session)
    assessment = assess_dialogue_quality(
        visible,
        player_input=player_input,
        profile=profile,
        recent_interactions=recent,
    )
    repaired = False
    if not assessment["acceptable"]:
        visible = build_profile_aware_dialogue_fallback(
            player_input=player_input,
            profile=profile,
            session=session,
            recent_interactions=recent,
        )
        assessment = assess_dialogue_quality(
            visible,
            player_input=player_input,
            profile=profile,
            recent_interactions=recent,
            allow_deterministic_fallback=True,
        )
        repaired = True

    output = deepcopy(result)
    _apply_visible_response(output, visible)
    diagnostics = {
        **assessment,
        "format_version": DIALOGUE_QUALITY_VERSION,
        "repaired": repaired,
        "repair_source": "profile_aware_deterministic_fallback_v1" if repaired else "provider_visible_response",
        "target_word_range": [TARGET_MIN_WORDS, TARGET_MAX_WORDS],
    }
    output["dialogue_quality"] = diagnostics
    nested = output.get("result")
    if isinstance(nested, dict):
        nested["dialogue_quality"] = deepcopy(diagnostics)
    return output


def assess_dialogue_quality(
    visible: dict[str, Any],
    *,
    player_input: str,
    profile: dict[str, Any] | None = None,
    recent_interactions: list[dict[str, Any]] | None = None,
    allow_deterministic_fallback: bool = False,
) -> dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    recent = recent_interactions or []
    narration = _text(visible.get("narration"))
    message = _npc_message(visible)
    speaker = _text(message.get("speaker"))
    line = _text(message.get("text"))
    combined = " ".join(part for part in (narration, line) if part)
    violations: list[str] = []
    warnings: list[str] = []

    if not speaker:
        violations.append("missing_npc_speaker")
    expected = _text(profile.get("name"))
    if expected and speaker and _normalize(expected) != _normalize(speaker):
        violations.append("speaker_mismatch")
    if not line:
        violations.append("missing_npc_line")
    line_words = _word_count(line)
    total_words = _word_count(combined)
    if line and line_words < _HARD_MIN_LINE_WORDS:
        violations.append("npc_line_too_brief")
    if total_words > _HARD_MAX_TOTAL_WORDS:
        violations.append("response_too_long")
    if total_words < TARGET_MIN_WORDS:
        warnings.append("below_target_word_range")
    if total_words > TARGET_MAX_WORDS:
        warnings.append("above_target_word_range")
    if line and _is_player_restatement(line, player_input):
        violations.append("player_input_restatement")
    lowered = combined.casefold()
    if any(phrase in lowered for phrase in _GENERIC_PHRASES):
        violations.append("generic_stock_phrase")

    leaked_terms = _private_leak_terms(profile, combined)
    if leaked_terms:
        violations.append("private_profile_leak")
    repeated = _near_duplicate_recent(line, recent)
    if repeated:
        violations.append("near_duplicate_recent_response")
    if not _has_specific_grounding(combined, profile):
        warnings.append("limited_profile_specificity")
    if not _looks_like_direct_answer(line, player_input):
        warnings.append("direct_answer_not_obvious")

    if allow_deterministic_fallback:
        violations = [item for item in violations if item not in {"npc_line_too_brief"}]
    return {
        "acceptable": not violations,
        "violations": violations,
        "warnings": warnings,
        "speaker": speaker,
        "line_words": line_words,
        "total_words": total_words,
        "private_leak_terms": leaked_terms,
        "near_duplicate_recent": repeated,
    }


def build_profile_aware_dialogue_fallback(
    *,
    player_input: str,
    profile: dict[str, Any] | None,
    session: dict[str, Any] | None,
    recent_interactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    session = session if isinstance(session, dict) else {}
    recent = recent_interactions or []
    speaker = _text(profile.get("name")) or _target_name(player_input) or "NPC"
    speaker_id = _text(profile.get("npc_id") or profile.get("id"))
    topic = _topic(player_input)
    repeated_topic = any(_topic(_text(item.get("player_input"))) == topic for item in recent[-6:])
    location = _location_name(session) or "the room"
    narration = _scene_action(speaker, topic, location)
    line = _fallback_line(
        speaker=speaker,
        topic=topic,
        repeated_topic=repeated_topic,
        profile=profile,
        location=location,
    )
    return {
        "format_version": "rpg_visible_response_v1",
        "narration": narration,
        "messages": [
            {
                "kind": "npc_dialogue",
                "speaker_id": speaker_id or None,
                "speaker": speaker,
                "text": line,
            }
        ],
        "plain_text": f'{narration}\n\n{speaker}: "{line}"',
        "npc": {
            "speaker_id": speaker_id or None,
            "speaker": speaker,
            "line": line,
        },
    }


def _fallback_line(
    *,
    speaker: str,
    topic: str,
    repeated_topic: bool,
    profile: dict[str, Any],
    location: str,
) -> str:
    is_bran = _normalize(speaker) == "bran"
    continuity = "Like I said, " if repeated_topic else ""
    if is_bran and topic == "business":
        return (
            f"{continuity}business is steady enough to keep the fire lit, but slower than I would like. "
            "The regulars still come through; it is the road traffic that has thinned this week. "
            "You came in from outside—did the old road seem unusually quiet to you?"
        )
    if is_bran and topic == "wellbeing":
        return (
            f"{continuity}my day has been steady, quiet, and a little too long. I have had worse days on the caravan road, "
            "but an empty common room gives a man too much time to count worries. Did you see many travelers on your way here?"
        )
    if is_bran and topic == "combat":
        return (
            f"{continuity}fancy styles have their place, but footing and judgment keep you alive. Mud, fear, and a bad angle "
            "will ruin a perfect stance faster than any master can correct it. Keep your guard honest and watch what your opponent does when pressed."
        )
    if is_bran and topic == "local_knowledge":
        return (
            f"{continuity}the old road carries most of the useful truth around here. Caravans, guards, and tired travelers all leave pieces of it at this bar. "
            "Lately those pieces have been fewer, which worries me more than loud rumors would."
        )
    public = _public_profile_sentence(profile)
    style = _speech_style_hint(profile)
    detail = public or f"Things around {location} have been steady, though conditions keep changing."
    hook = "What did you notice before you came in?"
    if topic == "wellbeing":
        detail = f"{speaker} has had a demanding but manageable day, with enough quiet to notice what others miss."
    elif topic == "opinion":
        detail = f"From practical experience, {speaker} trusts sound judgment more than showy certainty."
    prefix = f"{continuity}" if continuity else ""
    line = f"{prefix}{detail} {style} {hook}".strip()
    return re.sub(r"\s+", " ", line)


def _scene_action(speaker: str, topic: str, location: str) -> str:
    if _normalize(speaker) == "bran":
        if topic == "business":
            return "Bran rests the polishing rag on the counter and surveys the quiet common room."
        if topic == "wellbeing":
            return "Bran sets the glass down and rolls one tired shoulder before answering."
        if topic == "combat":
            return "Bran plants one broad hand on the counter, his old road scars catching the firelight."
        return "Bran glances toward the tavern window before answering in his plain, measured way."
    return f"{speaker} considers the question, briefly taking in {location} before answering."


def _apply_visible_response(result: dict[str, Any], visible: dict[str, Any]) -> None:
    narration = _text(visible.get("narration"))
    message = _npc_message(visible)
    npc = {
        "speaker_id": message.get("speaker_id"),
        "speaker": message.get("speaker"),
        "line": message.get("text"),
    }
    result["visible_response"] = {
        "narration": narration,
        "npc": deepcopy(npc),
    }
    result["final_narration"] = narration
    result["narration"] = narration
    result["summary"] = narration
    result["npc"] = deepcopy(npc)
    result["canonical_visible_response"] = deepcopy(visible)
    for key in ("result", "resolved_result"):
        nested = result.get(key)
        if not isinstance(nested, dict):
            continue
        nested["visible_response"] = deepcopy(result["visible_response"])
        nested["final_narration"] = narration
        nested["narration"] = narration
        nested["summary"] = narration
        nested["npc"] = deepcopy(npc)


def _is_nonstateful_direct_dialogue(result: dict[str, Any]) -> bool:
    sources = (result, _dict(result.get("result")), _dict(result.get("resolved_result")))
    stateful = _first_value(sources, "stateful")
    action = _text(_first_value(sources, "action_type", "semantic_action_type"))
    family = _text(_first_value(sources, "semantic_family"))
    visible = build_visible_response(result)
    return stateful is not True and bool(_npc_message(visible)) and (
        action == "npc_interpretive_dialogue" or family == "social"
    )


def _addressed_profile(
    result: dict[str, Any],
    session: dict[str, Any],
    visible: dict[str, Any],
) -> dict[str, Any]:
    message = _npc_message(visible)
    speaker_id = _text(message.get("speaker_id"))
    speaker = _text(message.get("speaker"))
    simulation = _dict(session.get("simulation_state"))
    runtime = _dict(session.get("runtime_state"))
    candidates: list[dict[str, Any]] = []
    for container in (
        _dict(simulation.get("npc_index")),
        _dict(runtime.get("npc_index")),
        _dict(_dict(simulation.get("social_state")).get("profiles")),
        _dict(_dict(runtime.get("social_state")).get("profiles")),
        _dict(_dict(_dict(result.get("first_call_grounding_diagnostics")).get("turn_grounding_packet")).get("npc_context")),
    ):
        for key, value in container.items():
            if isinstance(value, dict):
                candidates.append({"id": key, **value})
    packet = _dict(_dict(result.get("first_call_grounding_diagnostics")).get("turn_grounding_packet"))
    npc_context = _dict(packet.get("npc_context"))
    candidates.extend(item for item in npc_context.get("addressed_npcs", []) if isinstance(item, dict))
    for profile in candidates:
        ids = {
            _normalize(profile.get("id")),
            _normalize(profile.get("npc_id")),
            _normalize(profile.get("name")),
        }
        if _normalize(speaker_id) in ids or _normalize(speaker) in ids:
            return deepcopy(profile)
    return {"id": speaker_id, "npc_id": speaker_id, "name": speaker}


def _recent_interactions(session: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = _dict(session.get("runtime_state"))
    value = runtime.get("recent_interactions")
    if not isinstance(value, list):
        timeline = _dict(runtime.get("interaction_timeline"))
        value = timeline.get("events")
    return [item for item in (value or []) if isinstance(item, dict)][-12:]


def _private_leak_terms(profile: dict[str, Any], text: str) -> list[str]:
    private_values: list[str] = []
    biography = _dict(profile.get("biography"))
    inventory = _dict(profile.get("inventory"))
    for value in (biography.get("private"),):
        if isinstance(value, str):
            private_values.append(value)
    for value in inventory.get("private", []) if isinstance(inventory.get("private"), list) else []:
        if isinstance(value, str):
            private_values.append(value)
    boundaries = _dict(profile.get("knowledge_boundaries"))
    forbidden = boundaries.get("must_not_reveal")
    if isinstance(forbidden, list):
        private_values.extend(str(value) for value in forbidden)
    normalized_text = _normalize(text)
    leaks: list[str] = []
    for value in private_values:
        for phrase in _distinctive_phrases(value):
            if len(phrase.split()) >= 3 and phrase in normalized_text:
                leaks.append(phrase)
    return sorted(set(leaks))


def _distinctive_phrases(value: str) -> list[str]:
    words = _normalize(value).split()
    if len(words) <= 8:
        return [" ".join(words)] if words else []
    return [" ".join(words[index:index + 5]) for index in range(0, len(words) - 4)]


def _near_duplicate_recent(line: str, recent: list[dict[str, Any]]) -> bool:
    current = set(_normalize(line).split())
    if len(current) < 6:
        return False
    for event in recent[-6:]:
        prior = _text(event.get("npc_line"))
        if not prior:
            prior_visible = _dict(event.get("visible_response"))
            prior = _text(_npc_message(prior_visible).get("text"))
        prior_words = set(_normalize(prior).split())
        if len(prior_words) < 6:
            continue
        overlap = len(current & prior_words) / max(1, len(current | prior_words))
        if overlap >= 0.72:
            return True
    return False


def _has_specific_grounding(text: str, profile: dict[str, Any]) -> bool:
    normalized = _normalize(text)
    public = _normalize(_dict(profile.get("biography")).get("public"))
    values = _dict(profile.get("personality")).get("values")
    tokens = set(public.split())
    if isinstance(values, list):
        for value in values:
            tokens.update(_normalize(value).split())
    tokens -= {"the", "and", "that", "with", "from", "this", "his", "her", "their", "they", "have"}
    return any(len(token) >= 5 and token in normalized for token in tokens)


def _looks_like_direct_answer(line: str, player_input: str) -> bool:
    if not line:
        return False
    topic = _topic(player_input)
    topic_terms = {
        "business": {"business", "steady", "regulars", "road", "trade", "rooms", "food"},
        "wellbeing": {"day", "fine", "steady", "tired", "worse", "quiet"},
        "combat": {"guard", "footing", "stance", "blow", "fight", "combat"},
        "local_knowledge": {"road", "town", "travelers", "guards", "rumors"},
        "opinion": {"think", "trust", "prefer", "judgment", "believe"},
    }.get(topic, set())
    normalized = set(_normalize(line).split())
    return not topic_terms or bool(topic_terms & normalized)


def _topic(text: str) -> str:
    value = _normalize(text)
    if any(term in value for term in ("business", "customers", "patrons", "trade", "tavern doing")):
        return "business"
    if any(term in value for term in ("your day", "how are you", "how do you feel", "doing today", "going")):
        return "wellbeing"
    if any(term in value for term in ("sword", "combat", "fight", "guard", "battle")):
        return "combat"
    if any(term in value for term in ("road", "town", "rumor", "around here", "local")):
        return "local_knowledge"
    if any(term in value for term in ("think", "opinion", "prefer", "believe")):
        return "opinion"
    if any(term in value for term in ("who are you", "your name", "about yourself")):
        return "identity"
    return "general"


def _location_name(session: dict[str, Any]) -> str:
    state = _dict(session.get("state"))
    simulation = _dict(session.get("simulation_state"))
    scene = _dict(state.get("scene")) or _dict(simulation.get("scene"))
    return _text(scene.get("location_name") or scene.get("location") or state.get("location"))


def _public_profile_sentence(profile: dict[str, Any]) -> str:
    public = _text(_dict(profile.get("biography")).get("public"))
    return public.split(".")[0].strip() + "." if public else ""


def _speech_style_hint(profile: dict[str, Any]) -> str:
    style = _text(_dict(profile.get("personality")).get("speech_style"))
    if not style:
        return ""
    first = style.split(".")[0].strip()
    return f"Speaking plainly, {first[:1].lower() + first[1:]}." if first else ""


def _target_name(player_input: str) -> str:
    match = re.search(r"\b(?:ask|tell|speak to|talk to)\s+([A-Z][\w'-]+|[a-z][\w'-]+)", player_input)
    if not match:
        return ""
    value = match.group(1)
    return value[:1].upper() + value[1:]


def _npc_message(visible: dict[str, Any]) -> dict[str, Any]:
    messages = visible.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if isinstance(item, dict) and _text(item.get("kind")) == "npc_dialogue":
                return item
    npc = _dict(visible.get("npc"))
    if npc:
        return {
            "speaker_id": npc.get("speaker_id") or npc.get("npc_id") or npc.get("id"),
            "speaker": npc.get("speaker") or npc.get("name"),
            "text": npc.get("line") or npc.get("text"),
        }
    return {}


def _first_value(sources: tuple[dict[str, Any], ...], *keys: str) -> Any:
    for source in sources:
        for key in keys:
            if source.get(key) is not None:
                return source.get(key)
    return None


def _is_player_restatement(line: str, player_input: str) -> bool:
    line_normalized = _normalize(line)
    input_normalized = _normalize(player_input)
    if not line_normalized or not input_normalized:
        return False
    return line_normalized == input_normalized or (
        input_normalized in line_normalized and len(line_normalized) <= len(input_normalized) + 35
    )


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
