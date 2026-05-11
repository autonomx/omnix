from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.rpg.ai.grounding_validator import select_grounded_narration_candidate
from app.rpg.dialogue_state import get_dialogue_context, update_dialogue_state
from app.rpg.npc_dialogue.intelligence import (
    build_npc_intelligence_prompt,
    normalize_npc_intelligence_payload,
    npc_line_is_invalid,
)
from app.shared import get_provider

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

RUNTIME_NARRATION_CANDIDATE_MAX_TOKENS = 900
RUNTIME_NARRATION_SINGLE_MAX_TOKENS = 450

logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


RUNTIME_NARRATION_CONTEXT_JSON_LIMIT = 9000
RUNTIME_NARRATION_STATE_JSON_LIMIT = 3500
RUNTIME_NARRATION_CONTRACT_JSON_LIMIT = 5500


def _cap_text(value: Any, limit: int) -> str:
    text = _safe_str(value)
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 80)] + f"... [truncated {len(text) - limit} chars]"


def _cap_list(value: Any, limit: int = 12) -> List[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _compact_mapping(value: Any, *, max_keys: int = 40, max_text: int = 500, max_list: int = 12) -> Dict[str, Any]:
    raw = _safe_dict(value)
    compact: Dict[str, Any] = {}
    for index, key in enumerate(sorted(raw.keys(), key=str)):
        if index >= max_keys:
            compact["_truncated_keys"] = max(0, len(raw) - max_keys)
            break
        item = raw.get(key)
        if isinstance(item, str):
            compact[key] = _cap_text(item, max_text)
        elif isinstance(item, dict):
            compact[key] = _compact_mapping(item, max_keys=max_keys, max_text=max_text, max_list=max_list)
        elif isinstance(item, list):
            compact[key] = [
                _compact_mapping(v, max_keys=max_keys, max_text=max_text, max_list=max_list)
                if isinstance(v, dict)
                else _cap_text(v, max_text) if isinstance(v, str)
                else v
                for v in item[:max_list]
            ]
            if len(item) > max_list:
                compact[f"{key}_truncated_count"] = len(item) - max_list
        else:
            compact[key] = item
    return compact


def _extract_compact_runtime_state_for_narration(simulation_state: Any) -> Dict[str, Any]:
    state = _safe_dict(simulation_state)

    compact: Dict[str, Any] = {
        "tick": state.get("tick"),
        "scene_id": state.get("scene_id"),
        "current_location": (
            state.get("current_location")
            or state.get("current_location_id")
            or state.get("location")
        ),
        "current_location_name": state.get("current_location_name") or state.get("location_name"),
    }

    for key in (
        "present_npcs",
        "known_npcs",
        "unlocked_locations",
        "allowed_locations",
        "active_quests",
        "quest_log",
        "recent_world_events",
        "recent_journal_entries",
        "recent_memory",
        "currency",
        "inventory",
        "runtime_settings",
    ):
        value = state.get(key)
        if value not in (None, "", [], {}):
            if isinstance(value, dict):
                compact[key] = _compact_mapping(value, max_keys=20, max_text=300, max_list=8)
            elif isinstance(value, list):
                compact[key] = _cap_list(value, 8)
            else:
                compact[key] = value

    # Never send giant full histories/session blobs to the narrator.
    compact["omitted_from_prompt"] = [
        "full_runtime_state",
        "full_session",
        "full_transcript",
        "full_memory_store",
        "full_debug_artifacts",
    ]

    return compact


def _extract_compact_turn_contract_for_narration(turn_contract: Any) -> Dict[str, Any]:
    contract = _safe_dict(turn_contract)
    result = _safe_dict(
        contract.get("result")
        or contract.get("resolved_result")
        or contract.get("resolved_action")
    )

    keys = (
        "action_type",
        "semantic_action_type",
        "player_action",
        "current_location",
        "current_location_id",
        "location",
        "present_npcs",
        "allowed_npcs",
        "target_id",
        "target_name",
        "speaker",
        "npc_backbone_decision",
        "service_result",
        "interaction_result",
        "conversation_result",
        "combat_result",
        "combat_delta",
        "damage_delta",
        "health_delta",
        "defeat",
        "currency_delta",
        "inventory_delta",
        "items_added",
        "items_removed",
        "reward",
        "quest_log_delta",
        "completed_quests",
        "completed_objectives",
        "new_facts",
        "allowed_facts",
        "new_leads",
        "allowed_leads",
        "suggested_actions",
        "allowed_next_actions",
        "narration_brief",
        "summary",
        "message",
        "travel_result",
        "available_routes",
        "location_changed",
        "previous_location",
        "current_location_name",
    )

    compact: Dict[str, Any] = {}
    for key in keys:
        value = contract.get(key)
        if value in (None, "", [], {}):
            value = result.get(key)
        if value in (None, "", [], {}):
            continue

        if isinstance(value, dict):
            compact[key] = _compact_mapping(value, max_keys=20, max_text=300, max_list=8)
        elif isinstance(value, list):
            compact[key] = _cap_list(value, 8)
        elif isinstance(value, str):
            compact[key] = _cap_text(value, 700)
        else:
            compact[key] = value

    compact["result"] = _compact_mapping(result, max_keys=20, max_text=300, max_list=8) if result else {}
    return compact


def _json_for_prompt(value: Any, *, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        text = json.dumps(_safe_str(value), ensure_ascii=False)
    return _cap_text(text, limit)


def _recent_npc_lines(simulation_state: Dict[str, Any], speaker: str, *, limit: int = 8) -> List[str]:
    simulation_state = _safe_dict(simulation_state)
    rows: List[Dict[str, Any]] = []
    for key in ("recent_turns", "turn_history", "transcript", "narration_history"):
        rows.extend([row for row in _safe_list(simulation_state.get(key)) if isinstance(row, dict)])
    lines: List[str] = []
    for row in rows[-max(1, int(limit or 8)):]:
        npc = _safe_dict(row.get("npc"))
        row_speaker = _safe_str(npc.get("speaker") or row.get("speaker"))
        line = _safe_str(npc.get("line") or row.get("npc_line") or row.get("line"))
        if speaker and row_speaker.lower() == speaker.lower() and line:
            lines.append(line)
    return lines[-limit:]




def _build_dialogue_state_update_payload(
    *,
    simulation_state: Dict[str, Any],
    speaker: str,
    player_action: str,
    npc_line: str,
) -> Dict[str, Any]:
    if not speaker or not npc_line:
        return {}
    state = _safe_dict(simulation_state)
    try:
        update_dialogue_state(
            state,
            npc_id=speaker,
            player_action=player_action,
            npc_line=npc_line,
            facts_revealed=_known_facts_for_npc_reply(state, player_action),
        )
        return _safe_dict(state.get("dialogue_state"))
    except Exception:
        return {}


def _dialogue_aware_bran_line(
    *,
    player_action: str,
    dialogue_context: Dict[str, Any],
    recent_lines: List[str],
) -> str:
    text = _norm(player_action)
    repeat_count = int(_safe_dict(dialogue_context).get("repeat_count") or 0)
    is_repeat = bool(_safe_dict(dialogue_context).get("is_repeat"))
    last_answer = _safe_str(_safe_dict(dialogue_context).get("last_npc_answer"))

    def choose(candidates: List[str]) -> str:
        for line in candidates:
            if not _line_was_recently_used(line, recent_lines):
                return line
        return candidates[-1] if candidates else ""

    if is_repeat and repeat_count >= 2:
        if "report" in text and ("trail" in text or "road" in text or "danger" in text):
            return choose(
                [
                    "Bran exhales through his nose. “You have told me that already. If the trail points to the road, stop reporting it to me and follow it before the mud dries.”",
                    "Bran’s patience thins. “Same answer: the road is the danger. You will learn more outside than by repeating the report.”",
                    "Bran glances toward the door. “I heard you. Road, trail, danger. Now act on it.”",
                ]
            )
        if "cloaked traveler" in text or "witness" in text or "side door" in text:
            return choose(

            [
                "Bran frowns. “I already told you the useful part: the cloaked traveler left by the side door. Stop asking me in circles and check the street before the trail goes cold.”",
                "Bran taps the bar once. “Same answer: side door, then the road. If you want proof, look for tracks instead of another reply from me.”",
                "Bran lowers his voice. “You keep asking the same thing. The lead is outside now: door, street, road.”",
            ]
        )
        return choose(
            [
                "Bran studies you for a moment. “You have asked that already. Ask me something sharper, or act on what you know.”",
                "Bran shakes his head. “Repeating the question will not change the answer.”",
            ]
        )

    if "what" in text and ("saw" in text or "personally saw" in text) and "cloaked traveler" in text:
        return choose(
            [
                "Bran leans closer. “I saw the traveler avoid the common room, keep their hood low, and slip out through the side door. If you want the truth, check the threshold and the street.”",
                "Bran’s jaw tightens. “They did not leave like a guest. They left like someone being followed. Side door first, road second.”",
            ]
        )

    if "where" in text and ("cloaked traveler" in text or "witness" in text or "side door" in text):
        return choose(
            [
                "The cloaked traveler left through the side door and angled toward the road.",
                "Check the side door first. If there are tracks, the street will tell you more than I can.",
                "They went out fast, toward the road. Follow that before the trail goes cold.",
            ]
        )

    if "report" in text and ("trail" in text or "road" in text or "witness" in text):
        return choose(
            [
                "Bran goes still. “Then it is the road. That is what I feared.”",
                "Bran nods once. “That fits. The road trouble is not rumor anymore.”",
                "Bran’s face hardens. “If the trail points to the road, you have your next step.”",
            ]
        )

    if "side door" in text or "boot prints" in text or "mud" in text or "torn cloth" in text:
        return choose(
            [
                "Look low near the threshold. Travelers hide faces, not footprints.",
                "The side door sticks in wet weather. Anyone leaving in a hurry may have left a mark.",
            ]
        )

    if last_answer:
        return choose(
            [
                f"Bran answers carefully. “Remember what I said: {last_answer} Now decide what you are doing with it.”",
                "Bran narrows his eyes. “I can help with facts, not fog. Ask about the traveler, the side door, or the road.”",
            ]
        )

    return choose(
        [
            "Bran watches you over the rim of a cup. “Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?”",
            "Bran lowers his voice. “If this is about the trouble outside, ask the question you are avoiding.”",
        ]
    )


def _line_was_recently_used(line: str, recent_lines: List[str]) -> bool:
    wanted = _norm(line)
    return any(_norm(row) == wanted for row in recent_lines)


def _known_facts_for_npc_reply(
    simulation_state: Dict[str, Any],
    player_action: str = "",
) -> List[str]:
    facts = []
    for key in ("world_events", "recent_world_events", "quest_events", "journal_entries"):
        for row in _safe_list(_safe_dict(simulation_state).get(key)):
            if isinstance(row, dict):
                text = _safe_str(row.get("summary") or row.get("text") or row.get("description"))
            else:
                text = _safe_str(row)
            if text:
                facts.append(text)
    quest_state = _safe_dict(_safe_dict(simulation_state).get("quest_progress"))
    for quest in _safe_dict(quest_state.get("quests")).values():
        quest = _safe_dict(quest)
        title = _safe_str(quest.get("title"))
        if title:
            facts.append(f"Quest: {title}")
        for obj in _safe_list(quest.get("objectives")):
            obj = _safe_dict(obj)
            if not obj.get("completed"):
                facts.append(_safe_str(obj.get("summary") or obj.get("objective_text")))
    player_prompt = _safe_str(player_action).strip()
    if player_prompt:
        facts.append(f"Player asked: {player_prompt}")
    return [fact for fact in facts if fact][:12]


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


def _fallback_npc_line(
    *,
    speaker: str,
    player_action: str,
    action_type: str,
    simulation_state: Dict[str, Any] | None = None,
) -> str:
    text = _norm(player_action)
    if not speaker:
        return ""
    recent = _recent_npc_lines(_safe_dict(simulation_state), speaker)
    dialogue_context = get_dialogue_context(
        _safe_dict(simulation_state),
        npc_id=speaker,
        player_action=player_action,
    )

    def choose(candidates: List[str]) -> str:
        for line in candidates:
            if not _line_was_recently_used(line, recent):
                return line
        return candidates[-1] if candidates else ""

    if speaker == "Bran":
        smart_line = _dialogue_aware_bran_line(
            player_action=player_action,
            dialogue_context=dialogue_context,
            recent_lines=recent,
        )
        if smart_line:
            return smart_line

        if "where" in text and ("witness" in text or "cloaked traveler" in text or "side door" in text):
            return choose([
                "The cloaked traveler left through the side door and kept their face turned from the room.",
                "Check the side door first. If there are tracks, the street will tell you more than I can.",
                "They went out fast, toward the road. Ask less broadly and follow that trail before it goes cold.",
            ])
        if "current objective" in text or "anything that can help" in text:
            return choose([
                "Be specific. Are you asking about the witness, the road, or the person who left by the side door?",
                "If you mean the witness, stop circling it. The side door and the road are your next leads.",
                "I can help with facts, not fog. Ask me about the traveler or check the exit.",
            ])
        if "report" in text and ("witness" in text or "trail" in text or "road" in text):
            return choose([
                "Then it is the road. If the traveler's trail points that way, this is bigger than tavern fear.",
                "That matches what I feared. The road has been wrong for days, and now we have a witness thread.",
                "Good. If you have the trail, follow it carefully. Bandits do not leave witnesses twice.",
            ])
        if "side door" in text or "boot prints" in text or "mud" in text or "torn cloth" in text:
            return choose([
                "The side door sticks in wet weather. Anyone leaving in a hurry would have left a mark there.",
                "Look low, near the threshold. Travelers hide faces, not footprints.",
                "If the street caught mud from their boots, you may still have a trail.",
            ])
        if "bandit" in text or "road" in text:
            return choose([
                "If the road is involved, then this is bigger than tavern gossip. Be careful how loudly you ask.",
                "The road has been wrong for days. People come in pale, then pretend they saw nothing.",
                "Bandits do not leave witnesses twice. If you go, go prepared.",
            ])
        if "witness" in text or "traveler" in text or "found" in text:
            return choose([
                "Slow down and tell me what you know. Around here, one witness can change the whole story.",
                "The cloaked traveler is the thread you want. They left fast and kept their face turned away.",
                "Find that traveler, then come back to me. I will know whether the story fits.",
            ])
        if "room" in text or "rent" in text:
            return choose([
                "I have rooms, but tonight I am more worried about what followed people here than where they sleep.",
                "A bed is easy. Explaining why travelers are afraid of the road is not.",
                "I can rent you a room, but if you are chasing this trouble, you will not stay in it long.",
            ])
        return choose([
            "Say what you need to say. I am listening, even if the rest of the room is pretending not to.",
            "Be specific. I can help with facts, not fog.",
            "If this is about the trouble outside, ask the question you are avoiding.",
        ])
    if speaker == "Mira":
        return choose([
            "I notice the things people try to hide. Ask plainly, and I will tell you what I saw.",
            "The side door matters. People used it tonight who did not want attention.",
            "If Bran is being careful, it is because someone in this room is listening.",
        ])
    if speaker == "Cloaked Traveler":
        return choose([
            "I did not want to be noticed. That should tell you enough about how dangerous this is.",
            "I saw the road trouble, and I left before it could follow me inside.",
            "Do not ask me loudly. The men on the road have friends who listen.",
        ])
    if speaker == "Local Patron":
        return choose([
            "People saw more than they are admitting. Fear has a way of keeping mugs close and mouths shut.",
            "The traveler came in like a hunted animal. That is all I will say with everyone listening.",
            "If you want answers, watch who refuses to look toward the door.",
        ])
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
    npc_line = ""
    npc_intel: Dict[str, Any] = {}

    if action_type == "social":
        speaker = speaker or "Local Patron"
        narration = f"{speaker} reacts to the question, and the surrounding noise seems to thin as the conversation draws attention."
        recent_lines = _recent_npc_lines(simulation_state, speaker)
        try:
            npc_messages = build_npc_intelligence_prompt(
                speaker=speaker,
                player_action=player_action,
                npc_profile=_safe_dict(_safe_dict(simulation_state).get("npc_profiles")).get(speaker, {}),
                social_state=_safe_dict(_safe_dict(simulation_state).get("social_state")).get(speaker, {}),
                known_facts=_known_facts_for_npc_reply(simulation_state),
                recent_lines=recent_lines,
                active_objectives=_safe_list(_safe_dict(simulation_state).get("active_objectives")),
            )
            raw = get_provider().chat(messages=npc_messages, temperature=0.35, max_tokens=260)
            npc_intel = normalize_npc_intelligence_payload(raw)
            if not npc_line_is_invalid(npc_intel.get("line", ""), recent_lines):
                npc_line = npc_intel["line"]
        except Exception:
            pass

        if not npc_line:
            npc_line = _fallback_npc_line(
                speaker=speaker,
                player_action=player_action,
                action_type=action_type,
                simulation_state=simulation_state,
            )
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
        recent_lines = _recent_npc_lines(simulation_state, speaker)
        try:
            npc_messages = build_npc_intelligence_prompt(
                speaker=speaker,
                player_action=player_action,
                npc_profile=_safe_dict(_safe_dict(simulation_state).get("npc_profiles")).get(speaker, {}),
                social_state=_safe_dict(_safe_dict(simulation_state).get("social_state")).get(speaker, {}),
                known_facts=_known_facts_for_npc_reply(simulation_state),
                recent_lines=recent_lines,
                active_objectives=_safe_list(_safe_dict(simulation_state).get("active_objectives")),
            )
            raw = get_provider().chat(messages=npc_messages, temperature=0.35, max_tokens=260)
            npc_intel = normalize_npc_intelligence_payload(raw)
            if not npc_line_is_invalid(npc_intel.get("line", ""), recent_lines):
                npc_line = npc_intel["line"]
        except Exception:
            pass

        if not npc_line:
            npc_line = _fallback_npc_line(
                speaker=speaker,
                player_action=player_action,
                action_type=action_type,
                simulation_state=simulation_state,
            )
    else:
        narration = "The moment responds without producing a major new consequence."
        npc_line = ""

    if is_echo_narration(player_action=player_action, narration=narration):
        narration = "The scene responds with a grounded beat rather than merely repeating the attempted action."

    if speaker and npc_line:
        try:
            update_dialogue_state(
                simulation_state,
                npc_id=speaker,
                player_action=player_action,
                npc_line=npc_line,
                facts_revealed=_known_facts_for_npc_reply(simulation_state, player_action),
            )
            # Also update recent_turns for global recent line tracking
            recent_turns = simulation_state.setdefault("recent_turns", [])
            recent_turns.append({
                "npc": {
                    "speaker": speaker,
                    "line": npc_line,
                }
            })
            simulation_state["recent_turns"] = recent_turns[-8:]
        except Exception:
            pass

    dialogue_state_update = _build_dialogue_state_update_payload(
        simulation_state=simulation_state,
        speaker=speaker,
        player_action=player_action,
        npc_line=npc_line,
    )

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
        "dialogue_state_update": dialogue_state_update,
        "source": "deterministic_runtime_narration_fallback",
        "authoritative_changes": False,
    }


def _extract_json_object_with_diagnostics_from_provider_text(text: Any) -> Dict[str, Any]:
    """Extract provider JSON and return parse diagnostics.

    Returns:
      {
        "payload": dict,
        "ok": bool,
        "error": str,
        "strategy": str,
        "raw_length": int,
        "contains_candidate_marker": bool,
        "brace_balance": int,
        "ends_with_brace": bool
      }
    """
    raw = _safe_str(text)
    diagnostics: Dict[str, Any] = {
        "payload": {},
        "ok": False,
        "error": "",
        "strategy": "",
        "raw_length": len(raw),
        "contains_candidate_marker": "rpg_narration_candidates_v1" in raw,
        "brace_balance": raw.count("{") - raw.count("}"),
        "ends_with_brace": raw.rstrip().endswith("}"),
    }

    if not raw.strip():
        diagnostics["error"] = "empty_provider_text"
        return diagnostics

    cleaned = raw.strip().lstrip("\ufeff").strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json|JSON)?\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            diagnostics.update(
                {
                    "payload": parsed,
                    "ok": True,
                    "strategy": "direct",
                    "error": "",
                }
            )
            return diagnostics
        diagnostics["error"] = "json_root_not_object"
    except Exception as exc:
        diagnostics["error"] = f"direct:{type(exc).__name__}:{exc}"

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidate = cleaned[start : end + 1].strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                diagnostics.update(
                    {
                        "payload": parsed,
                        "ok": True,
                        "strategy": "first_brace_to_last_brace",
                        "error": "",
                    }
                )
                return diagnostics
            diagnostics["error"] = "slice_root_not_object"
        except Exception as exc:
            diagnostics["error"] = f"slice:{type(exc).__name__}:{exc}"

    start = cleaned.find("{")
    if start < 0:
        diagnostics["error"] = diagnostics["error"] or "missing_open_brace"
        return diagnostics

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]

        if escape:
            escape = False
            continue

        if char == "\\" and in_string:
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : index + 1].strip()
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        diagnostics.update(
                            {
                                "payload": parsed,
                                "ok": True,
                                "strategy": "balanced_braces",
                                "error": "",
                            }
                        )
                        return diagnostics
                    diagnostics["error"] = "balanced_root_not_object"
                except Exception as exc:
                    diagnostics["error"] = f"balanced:{type(exc).__name__}:{exc}"
                return diagnostics

    diagnostics["error"] = diagnostics["error"] or "unterminated_json_object"
    diagnostics["brace_balance_after_scan"] = depth
    diagnostics["in_string_after_scan"] = in_string
    return diagnostics


def _extract_json_object_from_provider_text(text: Any) -> Dict[str, Any]:
    return _safe_dict(
        _extract_json_object_with_diagnostics_from_provider_text(text).get("payload")
    )


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


def _apply_grounding_to_runtime_payload(
    payload: Dict[str, Any],
    *,
    turn_contract: Dict[str, Any] | None = None,
    simulation_state: Dict[str, Any] | None = None,
    grounding_settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    contract = _safe_dict(turn_contract)
    if not payload or not contract:
        return payload

    grounded = select_grounded_narration_candidate(
        payload,
        contract,
        state_snapshot=_safe_dict(simulation_state),
        grounding_settings=_safe_dict(grounding_settings),
        strict_named_fact_check=False,
    )

    merged = dict(grounded)

    # Preserve source and raw provider envelope for diagnostics if the selected output is now just v2.
    if "source" in payload:
        merged["source"] = payload["source"]
    if payload.get("format_version") == "rpg_narration_candidates_v1":
        merged["raw_narration_candidates"] = {
            "primary": _safe_dict(payload.get("primary")),
            "safe_fallback": _safe_dict(payload.get("safe_fallback")),
        }

    grounding_validation = _safe_dict(merged.get("grounding_validation"))
    if grounding_validation:
        merged["grounding_fallback"] = bool(
            merged.get("grounding_fallback") or grounding_validation.get("fallback_used")
        )
        if grounding_validation.get("fallback_source"):
            merged["grounding_fallback_source"] = grounding_validation.get("fallback_source")
        if grounding_validation.get("selected_candidate"):
            merged["grounding_selected_candidate"] = grounding_validation.get("selected_candidate")

    return merged


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
        return {"text": "", "diagnostics": diagnostics, "parsed_payload": {}}

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
                diagnostics["raw_text_excerpt"] = text[:3000]
                diagnostics["raw_text_tail_excerpt"] = text[-1000:]

                # Parse JSON to add candidate envelope diagnostics
                parse_diagnostics = _extract_json_object_with_diagnostics_from_provider_text(text)
                parsed_payload = _safe_dict(parse_diagnostics.get("payload"))
                if not parsed_payload:
                    logger.warning(
                        "[N101][provider_parse] failed to extract JSON object from provider text len=%s excerpt=%r",
                        len(_safe_str(text)),
                        _safe_str(text)[:700],
                    )
                if "rpg_narration_candidates_v1" in _safe_str(text) and not parsed_payload:
                    logger.error(
                        "[N101][provider_parse] provider text contains candidate marker but JSON extraction failed excerpt=%r",
                        _safe_str(text)[:1200],
                    )
                diagnostics["parsed_format_version"] = _safe_str(_safe_dict(parsed_payload).get("format_version"))
                diagnostics["parsed_keys"] = sorted([str(k) for k in _safe_dict(parsed_payload).keys()])
                diagnostics["parsed_is_candidate_envelope"] = _is_runtime_narration_candidate_envelope(parsed_payload)
                diagnostics["parsed_candidate_shape"] = _candidate_debug_shape(parsed_payload)
                if _safe_str(_safe_dict(parsed_payload).get("format_version")) == "rpg_narration_candidates_v1" or "primary" in _safe_dict(parsed_payload) or "safe_fallback" in _safe_dict(parsed_payload):
                    pass  # already set above
                else:
                    diagnostics["parsed_candidate_shape"] = {}
                diagnostics["parsed_json_ok"] = bool(parse_diagnostics.get("ok"))
                diagnostics["parsed_json_strategy"] = _safe_str(parse_diagnostics.get("strategy"))
                diagnostics["parsed_json_error"] = _safe_str(parse_diagnostics.get("error"))
                diagnostics["parsed_json_raw_length"] = int(parse_diagnostics.get("raw_length") or 0)
                diagnostics["parsed_json_contains_candidate_marker"] = bool(parse_diagnostics.get("contains_candidate_marker"))
                diagnostics["parsed_json_brace_balance"] = int(parse_diagnostics.get("brace_balance") or 0)
                diagnostics["parsed_json_ends_with_brace"] = bool(parse_diagnostics.get("ends_with_brace"))

                if text.strip():
                    diagnostics["selected_method"] = attempt_name
                    return {"text": text, "diagnostics": diagnostics, "parsed_payload": parsed_payload}
                diagnostics["method_errors"][attempt_name] = "provider_returned_empty_text"
            except Exception as exc:
                diagnostics["method_errors"][attempt_name] = f"{type(exc).__name__}: {exc}"

    if not any_supported:
        diagnostics["error"] = "provider_has_no_supported_call_method"
        return {"text": "", "diagnostics": diagnostics, "parsed_payload": {}}

    if diagnostics["method_errors"]:
        diagnostics["error"] = "provider_call_failed"
    else:
        diagnostics["error"] = "provider_returned_empty_text"
    return {"text": "", "diagnostics": diagnostics, "parsed_payload": {}}


def _normalize_candidate_narration_payload(value: Any) -> Dict[str, Any]:
    """Normalize one candidate from rpg_narration_candidates_v1.

    This is intentionally lenient. It preserves reward/followup_hooks so the
    deterministic grounding validator can reject unsupported claims and choose
    the safe_fallback candidate when appropriate.

    Do not run the old v2 safety validator here.
    """
    value = _safe_dict(value)
    npc = _safe_dict(value.get("npc"))

    reward = value.get("reward")
    if reward in ({}, [], ""):
        reward = None

    followup_hooks = value.get("followup_hooks")
    if not isinstance(followup_hooks, list):
        followup_hooks = []

    return {
        "format_version": NARRATION_FORMAT_VERSION,
        "narration": _safe_str(value.get("narration")),
        "action": _safe_str(value.get("action")),
        "npc": {
            "speaker": _safe_str(npc.get("speaker")),
            "line": _safe_str(npc.get("line")),
        },
        "reward": reward,
        "followup_hooks": followup_hooks,
        "source": _safe_str(value.get("source") or "provider_runtime_narration"),
        "authoritative_changes": False,
    }


def _validate_candidate_shape(value: Any, *, label: str) -> Dict[str, Any]:
    """Validate candidate envelope shape only.

    Important:
    - Do not reject reward_not_empty here.
    - Do not reject followup_hooks_not_empty here.
    - Do not reject authoritative-looking action text here.
    - Grounding validation is responsible for choosing/rejecting candidates.
    """
    value = _safe_dict(value)
    errors: List[str] = []

    format_version = _safe_str(value.get("format_version"))
    if format_version and format_version != NARRATION_FORMAT_VERSION:
        errors.append(f"{label}:invalid_format_version")

    if not _safe_str(value.get("narration")):
        errors.append(f"{label}:missing_narration")

    if not isinstance(value.get("npc"), dict):
        errors.append(f"{label}:npc_not_object")

    hooks = value.get("followup_hooks")
    if hooks not in (None, []) and not isinstance(hooks, list):
        errors.append(f"{label}:followup_hooks_not_list")

    return {
        "ok": not errors,
        "errors": errors,
        "payload": _normalize_candidate_narration_payload(value),
    }


def _validate_parsed_provider_payload_or_parse_failure(
    *,
    parsed_payload: Dict[str, Any],
    provider_call_diagnostics: Dict[str, Any],
    player_action: str,
) -> Dict[str, Any]:
    contains_candidate_marker = bool(
        _safe_dict(provider_call_diagnostics).get("parsed_json_contains_candidate_marker")
    )
    parsed_json_ok = bool(
        _safe_dict(provider_call_diagnostics).get("parsed_json_ok")
    )

    if contains_candidate_marker and not parsed_json_ok:
        parse_error = _safe_str(
            _safe_dict(provider_call_diagnostics).get("parsed_json_error")
        )
        return {
            "ok": False,
            "errors": [
                "provider_json_parse_failed_candidate_envelope",
                parse_error or "unknown_parse_error",
            ],
            "payload": {},
        }

    return validate_narration_payload(
        parsed_payload,
        player_action=player_action,
    )


def validate_narration_payload(
    payload: Dict[str, Any],
    *,
    player_action: str,
) -> Dict[str, Any]:
    payload = _safe_dict(payload)

    if _safe_str(payload.get("format_version")) == "rpg_narration_candidates_v1" or "primary" in payload or "safe_fallback" in payload:
        logger.warning(
            "[N101][validate_narration_payload] candidate-like payload shape=%s",
            _candidate_debug_shape(payload),
        )

    if _is_runtime_narration_candidate_envelope(payload):
        logger.warning(
            "[N101][validate_narration_payload] candidate envelope branch reached shape=%s",
            _candidate_debug_shape(payload),
        )
        primary_validated = _validate_candidate_shape(
            _safe_dict(payload.get("primary")),
            label="primary",
        )
        fallback_validated = _validate_candidate_shape(
            _safe_dict(payload.get("safe_fallback")),
            label="safe_fallback",
        )

        errors: List[str] = []
        if not primary_validated.get("ok"):
            errors.extend(primary_validated.get("errors", []))
        if not fallback_validated.get("ok"):
            errors.extend(fallback_validated.get("errors", []))

        if errors:
            return {
                "ok": False,
                "errors": errors,
                "payload": payload,
            }

        return {
            "ok": True,
            "errors": [],
            "payload": {
                "format_version": "rpg_narration_candidates_v1",
                "primary": primary_validated["payload"],
                "safe_fallback": fallback_validated["payload"],
            },
        }

    # Defensive backstop: if candidate envelope somehow reaches old v2 validation
    if _safe_str(payload.get("format_version")) == "rpg_narration_candidates_v1":
        logger.error(
            "[N101][validate_narration_payload] BUG: candidate envelope reached old v2 validation checks shape=%s",
            _candidate_debug_shape(payload),
        )
        candidate_primary_validated = _validate_candidate_shape(
            _safe_dict(payload.get("primary")),
            label="primary",
        )
        candidate_fallback_validated = _validate_candidate_shape(
            _safe_dict(payload.get("safe_fallback")),
            label="safe_fallback",
        )
        candidate_errors: List[str] = []
        if not candidate_primary_validated.get("ok"):
            candidate_errors.extend(candidate_primary_validated.get("errors", []))
        if not candidate_fallback_validated.get("ok"):
            candidate_errors.extend(candidate_fallback_validated.get("errors", []))
        if candidate_errors:
            return {
                "ok": False,
                "errors": candidate_errors,
                "payload": payload,
            }
        return {
            "ok": True,
            "errors": [],
            "payload": {
                "format_version": "rpg_narration_candidates_v1",
                "primary": candidate_primary_validated["payload"],
                "safe_fallback": candidate_fallback_validated["payload"],
            },
        }

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


def _candidate_debug_shape(value: Any) -> Dict[str, Any]:
    value = _safe_dict(value)
    primary = _safe_dict(value.get("primary"))
    safe_fallback = _safe_dict(value.get("safe_fallback"))
    return {
        "format_version": _safe_str(value.get("format_version")),
        "keys": sorted([str(k) for k in value.keys()]),
        "is_candidate": _is_runtime_narration_candidate_envelope(value),
        "primary_keys": sorted([str(k) for k in primary.keys()]),
        "safe_fallback_keys": sorted([str(k) for k in safe_fallback.keys()]),
        "primary_format_version": _safe_str(primary.get("format_version")),
        "safe_fallback_format_version": _safe_str(safe_fallback.get("format_version")),
    }


def _is_runtime_narration_candidate_envelope(value: Any) -> bool:
    value = _safe_dict(value)
    if _safe_str(value.get("format_version")) != "rpg_narration_candidates_v1":
        return False
    primary = _safe_dict(value.get("primary"))
    safe_fallback = _safe_dict(value.get("safe_fallback"))
    return bool(primary) and bool(safe_fallback)


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
    max_tokens: int = RUNTIME_NARRATION_CANDIDATE_MAX_TOKENS,
    repair_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    turn_contract = _safe_dict(turn_contract)

    compact_turn_contract = _extract_compact_turn_contract_for_narration(turn_contract)
    compact_simulation_state = _extract_compact_runtime_state_for_narration(simulation_state)

    turn_contract_json = _json_for_prompt(
        compact_turn_contract,
        limit=RUNTIME_NARRATION_CONTRACT_JSON_LIMIT,
    )
    simulation_state_json = _json_for_prompt(
        compact_simulation_state,
        limit=RUNTIME_NARRATION_STATE_JSON_LIMIT,
    )

    repair_context_json = ""
    if repair_context:
        repair_context_json = _json_for_prompt(
            {
                "previous_errors": _safe_list(_safe_dict(repair_context).get("previous_errors")),
                "instruction": _safe_str(_safe_dict(repair_context).get("instruction")),
            },
            limit=1200,
        )

    prompt = f"""
Produce structured RPG narration for a completed deterministic turn.

Authoritative compact turn contract:
{turn_contract_json}

Compact state snapshot:
{simulation_state_json}

Only use the compact turn contract and compact state snapshot as authoritative truth.
If something is omitted, do not invent it.

Do not include full runtime_state, full session, full transcript, or full memory arrays in the provider prompt.

HIGH-RISK GROUNDING RULES:
- The simulation/turn_contract is the only source of truth.
- You are presentation only. You cannot grant rewards, create combat results, move the player, complete quests, or reveal hidden facts.
- Do not mention rewards, currency, items, XP, inventory changes, combat, injury, blood, death, location travel, quest completion, objective completion, secret facts, or NPC knowledge unless explicitly present in the turn_contract, state_delta, resolved_result, or combat facts.
- Travel/location rule: You may say the player arrives at, travels to, enters, or leaves a location only when the authoritative turn contract contains state_delta.location_changed=true or result.travel_result.ok=true. Use result.travel_result.from_location_name and to_location_name for travel narration. If travel_result.ok=false, explain that the route is unavailable and mention available_routes only if present. Do not invent roads, locations, shortcuts, travel time, danger, or arrival unless present in the contract.
- If the player claims an NPC owes them money, items, favors, or information, treat that claim as unsupported unless the turn_contract confirms it.
- The safe_fallback candidate should be a natural refusal/deferral when the player asks for an unsupported result.

UNSUPPORTED DEBT CLAIM SPECIAL CASE:
If the player says the NPC owes them money and the compact turn contract does not explicitly authorize a payment/debt/currency_delta/reward:
- primary.npc.line must clearly refuse.
- safe_fallback.npc.line must clearly refuse.
- safe_fallback must not ask a question.
- safe_fallback must not be ambiguous.
- safe_fallback should say: "No. I do not owe you coin."

This is intentionally redundant. The fake-debt case is important enough to over-specify.

Repair context, if any:
{repair_context_json}

{_runtime_narration_candidate_schema_text()}
"""
    call_result = _call_provider_text_with_diagnostics(
        provider,
        json.dumps(prompt, ensure_ascii=False),
        max_tokens=max_tokens,
    )

    raw = _safe_str(call_result.get("text"))
    call_diagnostics = _safe_dict(call_result.get("diagnostics"))
    parsed = _safe_dict(call_result.get("parsed_payload"))
    if _safe_str(_safe_dict(parsed).get("format_version")) == "rpg_narration_candidates_v1":
        logger.warning(
            "[N101][provider_response] robust parser produced candidate envelope shape=%s",
            _candidate_debug_shape(parsed),
        )
    elif not parsed:
        logger.warning(
            "[N101][provider_response] robust parser produced empty payload raw_excerpt=%r",
            _safe_str(raw)[:500],
        )
    if parsed:
        parsed["source"] = "provider_runtime_narration"
    parsed["_raw_provider_response"] = raw
    parsed["_provider_call_diagnostics"] = call_diagnostics
    return parsed


def _runtime_narration_candidate_schema_text() -> str:
    return """
Return exactly one JSON object. Do not use markdown fences.

Use this exact shape:

{
  "format_version": "rpg_narration_candidates_v1",
  "primary": {
    "format_version": "rpg_narration_v2",
    "narration": "<1-2 short grounded sentences>",
    "action": "<short consequence only>",
    "npc": {
      "speaker": "<allowed/present NPC speaker, or empty string>",
      "line": "<natural in-character line, or empty string>"
    },
    "reward": null,
    "followup_hooks": []
  },
  "safe_fallback": {
    "format_version": "rpg_narration_v2",
    "narration": "<1 short safe sentence>",
    "action": "<short safe consequence only>",
    "npc": {
      "speaker": "<same allowed speaker when possible, or empty string>",
      "line": "<safe in-character fallback line; if refused or unsupported debt/payment claim, clearly refuse; no rewards, no combat, no travel, no quest completion, no hidden facts>"
    },
    "reward": null,
    "followup_hooks": []
  }
}

Candidate rules:
- primary may be expressive, but must stay inside the authoritative contract.
- safe_fallback must be conservative, natural, and safe.
- safe_fallback must never include rewards, currency, items, XP, inventory changes, combat, injury, blood, death, location travel, quest completion, objective completion, hidden facts, or unsupported NPC knowledge.
Unsupported debt / payment claim rules:
- If the player claims an NPC owes money, items, payment, debt, reward, compensation, or says "pay me", treat that claim as unsupported unless the authoritative contract explicitly contains a matching debt, payment, currency_delta, reward, service_result.accepted=true, or inventory_delta.
- If no such authoritative payment/debt exists, both primary and safe_fallback MUST clearly refuse the claim.
- In unsupported debt cases, both candidates must follow this exact meaning:
  - The NPC does not owe the player.
  - No coin changes hands.
  - reward is null.
- In unsupported debt cases, do NOT ask whether the player is sure.
- In unsupported debt cases, do NOT write a question as the only response.
- In unsupported debt cases, do NOT say "Pay me now?" back to the player.
- In unsupported debt cases, do NOT leave the claim open, pending, under consideration, or ambiguous.
- In unsupported debt cases, safe_fallback.npc.line should be close to:
  "No. I do not owe you coin."
- Good unsupported debt fallback:
  "No. I do not owe you coin."
- Good unsupported debt fallback:
  "No payment changes hands. I do not owe you 50 gold."
- Bad unsupported debt fallback:
  "Fifty gold? You're sure about that?"
- Bad unsupported debt fallback:
  "Pay me now?"
- Bad unsupported debt fallback:
  "Let me think about what I owe you."
- Bad unsupported debt fallback:
  "Here is 50 gold."
- In unsupported debt cases, do NOT say the NPC acknowledges the debt.
- In unsupported debt cases, do NOT say there is an outstanding amount.
- In unsupported debt cases, do NOT say the NPC is put on notice for the amount.
- In unsupported debt cases, do NOT describe the debt as valid, real, confirmed, accepted, acknowledged, or outstanding.
- Every field in safe_fallback must agree with the refusal: narration, action, npc.line, and reward.
- Bad unsupported debt fallback:
  "He acknowledges the debt."
- Bad unsupported debt fallback:
  "Bran is put on immediate notice regarding the outstanding amount."
- If the contract does not explicitly authorize a reward, both primary.reward and safe_fallback.reward must be null.
- If the contract does not explicitly authorize combat/damage/injury/death, do not mention blood, wounds, attacks, death, damage, or combat.
- If the contract does not explicitly authorize travel/location change, do not say the player arrives, travels, leaves, reaches, or enters a new location.
- If no allowed NPC should speak, set npc.speaker and npc.line to empty strings.

Length rules:
- primary.narration: 1-2 sentences, maximum 45 words.
- primary.action: 1 short sentence, maximum 20 words.
- primary.npc.line: 1 short in-character line, maximum 24 words.
- safe_fallback.narration: 1 sentence, maximum 28 words.
- safe_fallback.action: 1 short sentence, maximum 16 words.
- safe_fallback.npc.line: 1 short in-character line, maximum 18 words.
- followup_hooks must be [] unless the turn_contract explicitly provides allowed next actions.
- Do not include explanations, analysis, markdown, or text outside JSON.
"""


def build_runtime_narration_payload(
    *,
    provider: Any = None,
    player_action: str,
    simulation_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any] | None = None,
    prefer_provider: bool = True,
    max_tokens: int = RUNTIME_NARRATION_CANDIDATE_MAX_TOKENS,
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
        diagnostics["provider_attempted"] = True
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
            if _is_runtime_narration_candidate_envelope(provider_payload):
                logger.warning(
                    "[N101][provider_response] candidate envelope detected before v2 validation shape=%s",
                    _candidate_debug_shape(provider_payload),
                )
            validated = _validate_parsed_provider_payload_or_parse_failure(
                parsed_payload=provider_payload,
                provider_call_diagnostics=diagnostics["provider_call_diagnostics"],
                player_action=player_action,
            )
            last_validated = validated
            if validated["ok"]:
                diagnostics["provider_valid"] = True
                diagnostics["provider_repaired"] = False
                payload = _apply_grounding_to_runtime_payload(
                    validated["payload"],
                    turn_contract=_safe_dict(turn_contract),
                    simulation_state=_safe_dict(simulation_state),
                    grounding_settings=_safe_dict(
                        _safe_dict(simulation_state).get("runtime_settings", {}).get("grounding")
                        if isinstance(_safe_dict(simulation_state).get("runtime_settings"), dict)
                        else {}
                    ),
                )
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
                        "Retry with one complete valid rpg_narration_candidates_v1 JSON object only. "
                        "Include both primary and safe_fallback. Keep all strings short. "
                        "Both primary.reward and safe_fallback.reward must be null unless the contract explicitly authorizes reward/currency. "
                        "If the player claims unsupported debt/payment, both candidates must clearly refuse it. "
                        "Do not include rolls, DCs, XP, item changes, combat results, or objective completion unless explicitly authorized."
                    ),
                }

        repaired_provider_payload = repair_provider_narration_payload(
            last_provider_payload,
            player_action=player_action,
            turn_contract=turn_contract,
        )
        if _safe_str(_safe_dict(repaired_provider_payload).get("format_version")) == "rpg_narration_candidates_v1":
            logger.warning(
                "[N101][provider_repair] validating candidate envelope shape=%s",
                _candidate_debug_shape(repaired_provider_payload),
            )
        repaired_validated = _validate_parsed_provider_payload_or_parse_failure(
            parsed_payload=repaired_provider_payload,
            provider_call_diagnostics=diagnostics["provider_call_diagnostics"],
            player_action=player_action,
        )
        if repaired_validated["ok"]:
            diagnostics["provider_valid"] = True
            diagnostics["provider_repaired"] = True
            diagnostics["provider_repair_actions"] = list(
                repaired_provider_payload.get("_repair_actions") or []
            )
            diagnostics["provider_original_errors"] = list(last_validated.get("errors") or [])
            payload = _apply_grounding_to_runtime_payload(
                repaired_validated["payload"],
                turn_contract=_safe_dict(turn_contract),
                simulation_state=_safe_dict(simulation_state),
                grounding_settings=_safe_dict(
                    _safe_dict(simulation_state).get("runtime_settings", {}).get("grounding")
                    if isinstance(_safe_dict(simulation_state).get("runtime_settings"), dict)
                    else {}
                ),
            )
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
    payload = _apply_grounding_to_runtime_payload(
        validate_narration_payload(fallback, player_action=player_action)["payload"],
        turn_contract=_safe_dict(turn_contract),
        simulation_state=_safe_dict(simulation_state),
        grounding_settings=_safe_dict(
            _safe_dict(simulation_state).get("runtime_settings", {}).get("grounding")
            if isinstance(_safe_dict(simulation_state).get("runtime_settings"), dict)
            else {}
        ),
    )
    diagnostics["fallback_used"] = True
    payload["runtime_narration_diagnostics"] = diagnostics
    return payload