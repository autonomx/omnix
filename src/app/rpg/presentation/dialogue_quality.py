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
    if not _is_nonstateful_direct_dialogue(result):
        return result
    session = session if isinstance(session, dict) else {}
    absent = _referenced_absent_visible_response(result, session, player_input)
    if absent:
        output = deepcopy(result)
        _apply_absent_visible_response(output, absent)
        output["dialogue_quality"] = {
            "acceptable": True,
            "violations": [],
            "warnings": [],
            "format_version": DIALOGUE_QUALITY_VERSION,
            "repaired": True,
            "repair_source": "authoritative_absent_npc_repair_v1",
            "target_word_range": [TARGET_MIN_WORDS, TARGET_MAX_WORDS],
        }
        return output
    visible = build_visible_response(result, player_input)
    visible = _repair_multi_speaker_visible_response(
        result,
        visible,
        session=session,
        player_input=player_input,
    )
    structured_messages = [
        item for item in visible.get("messages", []) if isinstance(item, dict)
    ]
    if len(structured_messages) > 1:
        profiles = _addressed_profiles(result)
        combined = _text(visible.get("plain_text"))
        leaked_terms = sorted(
            {
                term
                for profile in profiles
                for term in _private_leak_terms(profile, combined)
            }
        )
        if leaked_terms:
            for message in structured_messages:
                message["text"] = "I can answer only from what is known here and now."
            visible["plain_text"] = _compose_visible_plain_text(visible)
        output = deepcopy(result)
        _apply_visible_response(output, visible)
        output["dialogue_quality"] = {
            "acceptable": not leaked_terms,
            "violations": ["private_profile_leak"] if leaked_terms else [],
            "warnings": [],
            "format_version": DIALOGUE_QUALITY_VERSION,
            "repaired": True,
            "repair_source": "multi_speaker_structure_repair_v1",
            "private_leak_terms": leaked_terms,
            "target_word_range": [TARGET_MIN_WORDS, TARGET_MAX_WORDS],
        }
        return output
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
    if any(phrase in combined.casefold() for phrase in _GENERIC_PHRASES):
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
        violations = [item for item in violations if item != "npc_line_too_brief"]
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
        "npc": {"speaker_id": speaker_id or None, "speaker": speaker, "line": line},
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
    if topic == "wellbeing":
        detail = f"{speaker} has had a demanding but manageable day, with enough quiet to notice what others miss."
    elif topic == "opinion":
        detail = f"From practical experience, {speaker} trusts sound judgment more than showy certainty."
    line = f"{continuity}{detail} {style} What did you notice before you came in?"
    return re.sub(r"\s+", " ", line).strip()


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
    result["visible_response"] = {"narration": narration, "npc": deepcopy(npc)}
    result["final_narration"] = narration
    result["narration"] = narration
    result["summary"] = narration
    result["npc"] = deepcopy(npc)
    result["canonical_visible_response"] = deepcopy(visible)
    result["first_call_visible_response"] = {
        "canonical_visible_response": deepcopy(visible),
        "visible_response": deepcopy(visible),
    }
    for key in ("result", "resolved_result"):
        nested = result.get(key)
        if isinstance(nested, dict):
            nested.update(
                {
                    "visible_response": deepcopy(result["visible_response"]),
                    "final_narration": narration,
                    "narration": narration,
                    "summary": narration,
                    "npc": deepcopy(npc),
                    "canonical_visible_response": deepcopy(visible),
                    "first_call_visible_response": deepcopy(
                        result["first_call_visible_response"]
                    ),
                }
            )


def _apply_absent_visible_response(result: dict[str, Any], visible: dict[str, Any]) -> None:
    narration = _text(visible.get("narration"))
    result["visible_response"] = {"narration": narration, "npc": {}}
    result["final_narration"] = narration
    result["narration"] = narration
    result["summary"] = narration
    result["npc"] = {}
    result["canonical_visible_response"] = deepcopy(visible)
    result["first_call_visible_response"] = {
        "canonical_visible_response": deepcopy(visible),
        "visible_response": deepcopy(visible),
    }
    for key in ("result", "resolved_result"):
        nested = result.get(key)
        if isinstance(nested, dict):
            nested.update(
                {
                    "visible_response": deepcopy(result["visible_response"]),
                    "final_narration": narration,
                    "narration": narration,
                    "summary": narration,
                    "npc": {},
                    "canonical_visible_response": deepcopy(visible),
                    "first_call_visible_response": deepcopy(
                        result["first_call_visible_response"]
                    ),
                }
            )


def _referenced_absent_visible_response(
    result: dict[str, Any],
    session: dict[str, Any],
    player_input: str,
) -> dict[str, Any]:
    priority = _dict(_grounding_packet(result).get("priority_context"))
    absent_ids = [
        _text(value)
        for value in priority.get("referenced_absent_npc_ids", [])
        if _text(value)
    ]
    if not absent_ids:
        target = _target_name(player_input)
        profile = _npc_profile_by_name(session, target)
        npc_id = _text(profile.get("npc_id") or profile.get("id"))
        present_ids = _present_npc_ids(session)
        if npc_id and present_ids and npc_id not in present_ids:
            absent_ids = [npc_id]
    if not absent_ids:
        return {}
    npc_id = absent_ids[0]
    profile = _npc_profile_by_id(session, npc_id)
    name = _text(profile.get("name")) or npc_id.replace("npc:", "").replace("_", " ").title()
    location = _location_name(session) or "the current location"
    narration = f"{name} is not here; there is no sign of them in {location} at the moment."
    return {
        "format_version": "rpg_visible_response_v1",
        "narration": narration,
        "messages": [],
        "plain_text": narration,
    }


def _repair_multi_speaker_visible_response(
    result: dict[str, Any],
    visible: dict[str, Any],
    *,
    session: dict[str, Any],
    player_input: str,
) -> dict[str, Any]:
    profiles = _addressed_profiles(result)
    if len(profiles) < 2:
        profiles = _referenced_profiles_from_session(session, player_input)
    messages = [item for item in visible.get("messages", []) if isinstance(item, dict)]
    if len(profiles) < 2 or len(messages) != 1:
        return visible
    names = [_text(profile.get("name")) for profile in profiles]
    segments = [
        _text(
            _npc_message(
                build_profile_aware_dialogue_fallback(
                    player_input=player_input,
                    profile=profile,
                    session=session,
                    recent_interactions=_recent_interactions(session),
                )
            ).get("text")
        )
        for profile in profiles
    ]
    if any(not segment for segment in segments):
        return visible
    repaired = deepcopy(visible)
    repaired["messages"] = [
        {
            "kind": "npc_dialogue",
            "speaker_id": profile.get("id") or profile.get("npc_id"),
            "speaker": name,
            "text": segment,
        }
        for profile, name, segment in zip(profiles, names, segments)
    ]
    repaired["plain_text"] = _compose_visible_plain_text(repaired)
    return repaired


def _addressed_profiles(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _dict(_grounding_packet(result).get("npc_context")).get("addressed_npcs", [])
        if isinstance(item, dict) and _text(item.get("name"))
    ]


def _compose_visible_plain_text(visible: dict[str, Any]) -> str:
    narration = _text(visible.get("narration"))
    paragraphs = [narration] if narration else []
    paragraphs.extend(
        f'{_text(item.get("speaker"))}: "{_text(item.get("text"))}"'
        for item in visible.get("messages", [])
        if isinstance(item, dict)
    )
    return "\n\n".join(paragraphs)


def _grounding_packet(result: dict[str, Any]) -> dict[str, Any]:
    diagnostics = _dict(result.get("first_call_grounding_diagnostics"))
    if not diagnostics:
        diagnostics = _dict(_dict(result.get("result")).get("first_call_grounding_diagnostics"))
    return _dict(diagnostics.get("turn_grounding_packet"))


def _npc_profile_by_id(session: dict[str, Any], npc_id: str) -> dict[str, Any]:
    simulation = _dict(session.get("simulation_state"))
    runtime = _dict(session.get("runtime_state"))
    for container in (
        _dict(simulation.get("npc_index")),
        _dict(runtime.get("npc_index")),
        _dict(_dict(simulation.get("social_state")).get("profiles")),
        _dict(_dict(runtime.get("social_state")).get("profiles")),
    ):
        profile = container.get(npc_id)
        if isinstance(profile, dict):
            return deepcopy(profile)
    return {}


def _npc_profile_by_name(session: dict[str, Any], name: str) -> dict[str, Any]:
    normalized = _normalize(name)
    if not normalized:
        return {}
    for profile in _all_npc_profiles(session):
        if normalized in {
            _normalize(profile.get("name")),
            _normalize(profile.get("npc_id")),
            _normalize(profile.get("id")),
        }:
            return profile
    return {}


def _referenced_profiles_from_session(
    session: dict[str, Any],
    player_input: str,
) -> list[dict[str, Any]]:
    normalized_input = _normalize(player_input)
    present_ids = _present_npc_ids(session)
    profiles = []
    for profile in _all_npc_profiles(session):
        npc_id = _text(profile.get("npc_id") or profile.get("id"))
        name = _text(profile.get("name"))
        if (
            npc_id in present_ids
            and name
            and re.search(rf"\b{re.escape(_normalize(name))}\b", normalized_input)
        ):
            profiles.append(profile)
    return profiles[:3]


def _all_npc_profiles(session: dict[str, Any]) -> list[dict[str, Any]]:
    simulation = _dict(session.get("simulation_state"))
    runtime = _dict(session.get("runtime_state"))
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for container in (
        _dict(simulation.get("npc_index")),
        _dict(runtime.get("npc_index")),
        _dict(_dict(simulation.get("social_state")).get("profiles")),
        _dict(_dict(runtime.get("social_state")).get("profiles")),
    ):
        for key, value in container.items():
            if not isinstance(value, dict):
                continue
            profile = {"id": key, **value}
            npc_id = _text(profile.get("npc_id") or profile.get("id"))
            if npc_id and npc_id not in seen:
                seen.add(npc_id)
                profiles.append(profile)
    return profiles


def _present_npc_ids(session: dict[str, Any]) -> set[str]:
    simulation = _dict(session.get("simulation_state"))
    runtime = _dict(session.get("runtime_state"))
    scene = _dict(runtime.get("current_scene")) or _dict(runtime.get("scene")) or _dict(simulation.get("scene"))
    player = _dict(simulation.get("player_state"))
    values = [
        *list(scene.get("present_npc_ids") or []),
        *list(player.get("nearby_npc_ids") or []),
        *list(runtime.get("present_npc_ids") or []),
        *list(runtime.get("nearby_npc_ids") or []),
    ]
    for row in list(scene.get("nearby_npcs") or []) + list(scene.get("npcs") or []):
        if isinstance(row, dict):
            values.append(row.get("npc_id") or row.get("id"))
        elif isinstance(row, str):
            values.append(row)
    return {_text(value) for value in values if _text(value)}


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
    containers = (
        _dict(simulation.get("npc_index")),
        _dict(runtime.get("npc_index")),
        _dict(_dict(simulation.get("social_state")).get("profiles")),
        _dict(_dict(runtime.get("social_state")).get("profiles")),
    )
    for container in containers:
        for key, value in container.items():
            if isinstance(value, dict):
                candidates.append({"id": key, **value})
    packet = _grounding_packet(result)
    addressed = _dict(packet.get("npc_context")).get("addressed_npcs", [])
    candidates.extend(item for item in addressed if isinstance(item, dict))
    target_ids = {_normalize(speaker_id), _normalize(speaker)}
    for profile in candidates:
        ids = {_normalize(profile.get(key)) for key in ("id", "npc_id", "name")}
        if target_ids & ids:
            return deepcopy(profile)
    return {"id": speaker_id, "npc_id": speaker_id, "name": speaker}


def _recent_interactions(session: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = _dict(session.get("runtime_state"))
    value = runtime.get("recent_interactions")
    if not isinstance(value, list):
        value = _dict(runtime.get("interaction_timeline")).get("events")
    return [item for item in (value or []) if isinstance(item, dict)][-12:]


def _private_leak_terms(profile: dict[str, Any], text: str) -> list[str]:
    private_values: list[str] = []
    biography = _dict(profile.get("biography"))
    inventory = _dict(profile.get("inventory"))
    if isinstance(biography.get("private"), str):
        private_values.append(biography["private"])
    if isinstance(inventory.get("private"), list):
        private_values.extend(str(value) for value in inventory["private"])
    forbidden = _dict(profile.get("knowledge_boundaries")).get("must_not_reveal")
    if isinstance(forbidden, list):
        private_values.extend(str(value) for value in forbidden)
    normalized_text = _normalize(text)
    leaks: set[str] = set()
    for value in private_values:
        words = _normalize(value).split()
        phrases = [" ".join(words)] if len(words) <= 8 else [" ".join(words[i:i + 5]) for i in range(len(words) - 4)]
        leaks.update(phrase for phrase in phrases if len(phrase.split()) >= 3 and phrase in normalized_text)
    return sorted(leaks)


def _near_duplicate_recent(line: str, recent: list[dict[str, Any]]) -> bool:
    current = set(_normalize(line).split())
    if len(current) < 6:
        return False
    for event in recent[-6:]:
        prior = _text(event.get("npc_line"))
        if not prior:
            prior = _text(_npc_message(_dict(event.get("visible_response"))).get("text"))
        prior_words = set(_normalize(prior).split())
        if len(prior_words) >= 6 and len(current & prior_words) / max(1, len(current | prior_words)) >= 0.72:
            return True
    return False


def _has_specific_grounding(text: str, profile: dict[str, Any]) -> bool:
    normalized = _normalize(text)
    public = _normalize(_dict(profile.get("biography")).get("public"))
    tokens = set(public.split())
    values = _dict(profile.get("personality")).get("values")
    if isinstance(values, list):
        for value in values:
            tokens.update(_normalize(value).split())
    tokens -= {"the", "and", "that", "with", "from", "this", "his", "her", "their", "they", "have"}
    return any(len(token) >= 5 and token in normalized for token in tokens)


def _looks_like_direct_answer(line: str, player_input: str) -> bool:
    topic_terms = {
        "business": {"business", "steady", "regulars", "road", "trade", "rooms", "food"},
        "wellbeing": {"day", "fine", "steady", "tired", "worse", "quiet"},
        "combat": {"guard", "footing", "stance", "blow", "fight", "combat"},
        "local_knowledge": {"road", "town", "travelers", "guards", "rumors"},
        "opinion": {"think", "trust", "prefer", "judgment", "believe"},
    }.get(_topic(player_input), set())
    return bool(line) and (not topic_terms or bool(topic_terms & set(_normalize(line).split())))


def _topic(text: str) -> str:
    value = _normalize(text)
    if any(term in value for term in (
        "business", "customers", "patrons", "trade", "tavern doing", "ale is selling", "ale selling",
        "common room is empty", "common room empty", "rooms empty",
    )):
        return "business"
    if any(term in value for term in (
        "your day", "how are you", "how do you feel", "doing today", "going", "feels tired", "feel tired", "are you tired",
    )):
        return "wellbeing"
    if any(term in value for term in (
        "old road", "the road", "about the road", "town", "rumor", "around here", "local", "travelers",
        "guards still", "guards stop", "stop here", "road is safe",
    )):
        return "local_knowledge"
    if any(term in value for term in ("sword", "combat", "fight", "battle", "stance", "warrior")):
        return "combat"
    if any(term in value for term in ("think", "opinion", "prefer", "believe", "trustworthy")):
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
    first = style.split(".")[0].strip() if style else ""
    return f"Speaking plainly, {first[:1].lower() + first[1:]}." if first else ""


def _target_name(player_input: str) -> str:
    match = re.search(
        r"\b(?:ask(?:\s+for)?|tell|speak to|talk to)\s+([A-Z][\w'-]+|[a-z][\w'-]+)",
        player_input,
    )
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
    return {
        "speaker_id": npc.get("speaker_id") or npc.get("npc_id") or npc.get("id"),
        "speaker": npc.get("speaker") or npc.get("name"),
        "text": npc.get("line") or npc.get("text"),
    } if npc else {}


def _first_value(sources: tuple[dict[str, Any], ...], *keys: str) -> Any:
    for source in sources:
        for key in keys:
            if source.get(key) is not None:
                return source.get(key)
    return None


def _is_player_restatement(line: str, player_input: str) -> bool:
    line_normalized = _normalize(line)
    input_normalized = _normalize(player_input)
    return bool(line_normalized and input_normalized) and (
        line_normalized == input_normalized
        or input_normalized in line_normalized and len(line_normalized) <= len(input_normalized) + 35
    )


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
