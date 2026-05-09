from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.objectives.affordances import build_objective_affordances_for_state
from app.rpg.objectives.progression_rules import (
    extract_action_topics,
    infer_semantic_action,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def action_signature(action: str) -> str:
    lower = _safe_str(action).lower()
    semantic = infer_semantic_action(lower)
    topics = extract_action_topics(lower)
    return f"{semantic}:{':'.join(topics[:4])}"


def recent_action_signature_counts(transcript: List[Dict[str, Any]], *, limit: int = 8) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    recent = _safe_list(transcript)
    for row in recent[-max(1, int(limit or 8)):]:
        row = _safe_dict(row)
        action = _safe_str(row.get("player_action") or row.get("action"))
        if not action:
            continue
        sig = action_signature(action)
        counts[sig] = counts.get(sig, 0) + 1
    return counts


def is_repeated_affordance_action(action: str, transcript: List[Dict[str, Any]], *, threshold: int = 2) -> bool:
    sig = action_signature(action)
    return recent_action_signature_counts(transcript).get(sig, 0) >= int(threshold or 2)


AFFORDANCE_ROTATION_ORDER = {
    "ask": ["inspect", "travel", "follow", "report", "prepare", "confront"],
    "inspect": ["follow", "travel", "ask", "report", "prepare", "confront"],
    "travel": ["inspect", "follow", "ask", "report", "prepare", "confront"],
    "follow": ["inspect", "travel", "ask", "report", "prepare", "confront"],
    "report": ["travel", "inspect", "ask", "prepare", "confront"],
    "prepare": ["travel", "inspect", "ask", "confront", "report"],
}


def _semantic_of_action(action: str) -> str:
    return infer_semantic_action(_safe_str(action))


def choose_rotated_affordance(context: Dict[str, Any], repeated_action: str) -> str:
    repeated_semantic = _semantic_of_action(repeated_action)
    preferred = AFFORDANCE_ROTATION_ORDER.get(repeated_semantic, ["inspect", "travel", "ask", "report", "prepare"])
    candidates = []
    for row in build_objective_affordances_for_state(context, limit=20):
        command = _safe_str(_safe_dict(row).get("command")).strip()
        if not command:
            continue
        candidate_semantic = _semantic_of_action(command)
        candidates.append((command, candidate_semantic))

    repeated_sig = action_signature(repeated_action)
    recent_counts = recent_action_signature_counts(_safe_list(context.get("recent_turns")), limit=12)

    for wanted_semantic in preferred:
        for command, semantic in candidates:
            if semantic != wanted_semantic:
                continue
            sig = action_signature(command)
            if sig == repeated_sig:
                continue
            if recent_counts.get(sig, 0) >= 2:
                continue
            if is_meta_or_vague_action(command):
                continue
            return command

    for command, semantic in candidates:
        sig = action_signature(command)
        if sig != repeated_sig and recent_counts.get(sig, 0) < 2 and not is_meta_or_vague_action(command):
            return command

    return ""


def _dialogue_topic_repeat_count(context: Dict[str, Any], npc_id: str, topic: str) -> int:
    dialogue = _safe_dict(_safe_dict(context).get("dialogue_state"))
    topics = _safe_dict(dialogue.get("npc_topics"))
    row = _safe_dict(topics.get(f"{npc_id}:{topic}") or topics.get(f"{npc_id.lower()}:{topic}"))
    return int(row.get("repeat_count") or 0)


def _story_hook_fired(context: Dict[str, Any], hook_id: str) -> bool:
    hook_state = _safe_dict(_safe_dict(context).get("autoplay_story_hook_state"))
    fired = _safe_dict(hook_state.get("fired_hooks"))
    return hook_id in fired


def _quest_status(context: Dict[str, Any], quest_id: str) -> str:
    quest_progress = _safe_dict(context.get("quest_progress"))
    quests = _safe_dict(quest_progress.get("quests"))
    quest = _safe_dict(quests.get(quest_id))
    return _safe_str(quest.get("status"))


def _quest_completed(context: Dict[str, Any], quest_id: str) -> bool:
    quest_progress = _safe_dict(context.get("quest_progress"))
    quests = _safe_dict(quest_progress.get("quests"))
    quest = _safe_dict(quests.get(quest_id))
    return bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"



def _current_location(context: Dict[str, Any]) -> str:
    return _safe_str(
        context.get("current_location")
        or context.get("current_location_name")
        or _safe_dict(context.get("scene")).get("location")
        or _safe_dict(context.get("player_visible")).get("location")
    ).lower()


def _witness_facts(context: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(context.get("witness_search_facts"))


def _post_witness_road_transition_active(context: Dict[str, Any]) -> bool:
    location = _current_location(context)
    facts = _witness_facts(context)
    return bool(
        _quest_completed(context, "quest:witness_search")
        or _quest_status(context, "quest:bandit_road") == "active"
        or _story_hook_fired(context, "hook:witness:pursue_bandit_trail")
        or _story_hook_fired(context, "hook:travel:location:east_road_outside_tavern")
        or bool(facts.get("followed_road"))
        or "east_road" in location
        or "road outside" in location
        or "outside the rusty flagon" in location
    )


def _post_transition_forbidden_bran_or_witness_action(action: str) -> bool:
    lower = _safe_str(action).lower()
    forbidden = (
        "ask bran where the cloaked traveler",
        "ask bran what he personally saw",
        "ask bran what they personally saw",
        "report to bran that the cloaked traveler trail",
        "stop repeating the report to bran",
        "where the cloaked traveler went",
        "cloak markings",
        "witness search",
        "side door",
        "cloaked traveler went",
    )
    return any(term in lower for term in forbidden)


def _road_progression_action(context: Dict[str, Any], original_action: str = "") -> str:
    lower = _safe_str(original_action).lower()
    location = _current_location(context)

    if "road" not in location and "outside" not in location:
        return (
            "I leave the Rusty Flagon and follow the road outside, "
            "looking for fresh tracks, wagon ruts, black cord, or bridge signs."
        )

    if "prepare" in active_objective_blob(context):
        return (
            "I check my supplies, secure food and water, and prepare to follow "
            "the bandit road trail."
        )

    if "bridge" in lower:
        return (
            "I follow the road toward the mill bridge, watching for ambush signs, "
            "lantern marks, wagon ruts, or bandit tracks."
        )

    return (
        "I inspect the road outside the tavern for fresh tracks, wagon ruts, "
        "black cord, torn cloth, ambush signs, or bridge markings."
    )


META_ACTION_PATTERNS = (
    "current objective",
    "anything that can help",
    "what they know",
    "choose a concrete lead",
    "ask a named npc",
    "named npc",
    "travel toward the next known location",
    "next known location",
    "inspect a physical clue",
    "physical clue",
    "grounded way to make progress",
    "make progress on",
    "focus on the objective",
    "one specific question about the witness",
    "next concrete lead",
    "stop repeating",
    "stop repeating the report",
    "stop repeating the report to bran",
    # Added from rpg-design.txt meta-planner block
    "review my quest log",
    "review the quest log",
    "decide what objective to pursue",
    "choose next objective",
    "choose the next objective",
    "what objective to pursue next",
    "decide what to do next",
    "make progress",
    "look at my quest log",
)


COMMAND_LABEL_PATTERNS = (
    "ask bran what they personally saw",
    "ask bran what he personally saw",
    "investigate story arc",
    "travel toward the main road",
    "inspect the road trail",
    "inspect the trail where the traveler was seen",
    "ask bran one specific question about the witness",
)


def normalize_command_label_action(action: str) -> str:
    """Convert harness/imperative labels into first-person executable commands."""
    text = _safe_str(action).strip()
    lower = text.lower()
    if not text:
        return text

    if lower.startswith("ask bran what they personally saw") or lower.startswith("ask bran what he personally saw"):
        return "I ask Bran what he personally saw about the cloaked traveler, especially which door they used and where they went next."

    if lower.startswith("ask bran one specific question about the witness"):
        return "I ask Bran where the witness or cloaked traveler was last seen and what direction they went."

    if lower.startswith("investigate story arc") and "witness" in lower:
        return "I investigate the Witness Search by checking the tavern side door, the nearby street, and the road for signs of the cloaked traveler."

    if lower.startswith("travel toward the main road") or lower.startswith("travel toward"):
        return "I leave the Rusty Flagon and follow the road outside, looking for fresh tracks or the cloaked traveler."

    if lower.startswith("inspect the road trail"):
        return "I inspect the road outside the tavern for fresh tracks, disturbed mud, torn cloth, or signs of the cloaked traveler."

    if lower.startswith("inspect the trail where the traveler was seen"):
        return "I inspect the tavern side door and nearby street for mud, torn cloth, boot prints, or signs of a hurried exit."

    # Human-playable imperative actions are accepted, but normalize them to the
    # first-person style expected by the runtime parser.
    imperative_prefixes = (
        "ask ",
        "inspect ",
        "travel ",
        "follow ",
        "report ",
        "search ",
        "confront ",
        "leave ",
    )
    if lower.startswith(imperative_prefixes) and not lower.startswith("i "):
        return "I " + text[0].lower() + text[1:]

    return text


def is_meta_or_vague_action(action: str) -> bool:
    lower = _safe_str(action).lower()
    return (
        any(pattern in lower for pattern in META_ACTION_PATTERNS)
        or any(pattern in lower for pattern in COMMAND_LABEL_PATTERNS)
    )


def active_objective_blob(context: Dict[str, Any]) -> str:
    parts: List[str] = []
    for row in _safe_list(_safe_dict(context).get("active_objectives")):
        row = _safe_dict(row)
        parts.extend(
            [
                _safe_str(row.get("objective_id")),
                _safe_str(row.get("title")),
                _safe_str(row.get("summary")),
                _safe_str(row.get("objective_text")),
                _safe_str(row.get("description")),
            ]
        )
    objectives = _safe_dict(_safe_dict(context).get("objectives"))
    parts.extend(
        [
            _safe_str(objectives.get("active_objective")),
            _safe_str(objectives.get("known_goal")),
        ]
    )
    return " ".join(part for part in parts if part).lower()


def strongest_known_npc(context: Dict[str, Any]) -> str:
    for key in ("nearby_npcs", "present_npcs"):
        for row in _safe_list(_safe_dict(context).get(key)):
            row = _safe_dict(row)
            name = _safe_str(row.get("name") or row.get("npc_id")).strip()
            if name:
                if name.lower() in {"bran", "innkeeper", "bartender"}:
                    return "Bran"
                return name
    return "Bran"


def suggested_executable_action(context: Dict[str, Any], transcript: List[Dict[str, Any]] | None = None) -> str:
    """Pick an executable suggested action, ignoring planner/meta labels."""
    best_command = ""
    best_score = -10_000
    for row in _safe_list(_safe_dict(context).get("suggested_actions")):
        row = _safe_dict(row)
        command = _safe_str(row.get("command")).strip()
        if not command or is_meta_or_vague_action(command):
            continue
        lower_command = command.lower()
        if _post_witness_road_transition_active(context) and _post_transition_forbidden_bran_or_witness_action(command):
            continue
        if _quest_completed(context, "quest:witness_search") and any(
            phrase in lower_command
            for phrase in (
                "where the cloaked traveler went",
                "what he personally saw",
                "cloak markings",
                "report to bran",
                "witness search",
                "side door",
            )
        ):
            continue
        if transcript and is_repeated_affordance_action(command, transcript):
            continue
        category = _safe_str(row.get("category"))
        score = int(row.get("goal_pressure_score") or row.get("strategy_score") or row.get("priority") or 0)
        if category in {"objective", "quest_log", "story_arc", "travel", "exploration"}:
            score += 50
        lower = command.lower()
        if any(term in lower for term in ("where", "side door", "street", "road", "tracks", "trail", "report", "witness", "cloaked traveler")):
            score += 40
        if score > best_score:
            best_score = score
            best_command = command
    return best_command


def _handoff_action_from_committed_context(context: Dict[str, Any]) -> str:
    context = _safe_dict(context)
    commit_summary = _safe_dict(context.get("campaign_state_commit_summary"))
    quest_summary = _safe_dict(commit_summary.get("quest_progress_summary"))
    quests = _safe_list(quest_summary.get("quests"))
    if not quests:
        quests = list(_safe_dict(_safe_dict(context.get("quest_progress")).get("quests")).values())

    for quest in quests:
        quest = _safe_dict(quest)
        if quest.get("completed") or _safe_str(quest.get("status")) == "completed":
            continue
        title = _safe_str(quest.get("title"))
        is_handoff = (
            bool(quest.get("handoff_quest"))
            or quest.get("source") == "campaign_state_authority_commit"
            or title.startswith("Investigate Lead:")
        )
        if not is_handoff:
            continue
        lead = _safe_dict(quest.get("lead"))
        lead_label = _safe_str(
            lead.get("name")
            or lead.get("title")
            or title.replace("Investigate Lead:", "").strip()
        )
        for obj in _safe_list(quest.get("objectives")):
            obj = _safe_dict(obj)
            if obj.get("completed") or _safe_str(obj.get("status")) == "completed":
                continue
            suggested = _safe_list(obj.get("suggested_actions"))
            for action in suggested:
                action = _safe_str(action).strip()
                if action and not is_meta_or_vague_action(action):
                    return action
            subject = _safe_str(obj.get("subject") or lead_label or obj.get("summary") or title)
            if subject:
                return (
                    f"I investigate the lead: {subject}, checking the next place, person, "
                    "or evidence connected to it instead of repeating the old search."
                )
    return ""


def _has_active_committed_handoff_quest(context: Dict[str, Any]) -> bool:
    context = _safe_dict(context)
    commit_summary = _safe_dict(context.get("campaign_state_commit_summary"))
    quest_summary = _safe_dict(commit_summary.get("quest_progress_summary"))
    quests = _safe_list(quest_summary.get("quests"))
    if not quests:
        quests = list(_safe_dict(_safe_dict(context.get("quest_progress")).get("quests")).values())
    for quest in quests:
        quest = _safe_dict(quest)
        if quest.get("completed") or _safe_str(quest.get("status")) == "completed":
            continue
        if (
            bool(quest.get("handoff_quest"))
            or quest.get("source") == "campaign_state_authority_commit"
            or _safe_str(quest.get("title")).startswith("Investigate Lead:")
        ):
            return True
    return False


def executable_action_for_context(context: Dict[str, Any], original_action: str = "") -> str:
    """Convert meta/planner text into an executable world command."""
    context = _safe_dict(context)
    handoff_action = _handoff_action_from_committed_context(context)
    if handoff_action:
        return handoff_action
    lower_original = _safe_str(original_action).lower()
    objective_blob = active_objective_blob(context)
    npc = strongest_known_npc(context)
    location = _current_location(context)

    if _post_witness_road_transition_active(context):
        if _post_transition_forbidden_bran_or_witness_action(original_action) or is_meta_or_vague_action(original_action):
            return _road_progression_action(context, original_action)

    if _quest_completed(context, "quest:witness_search"):
        if "road" not in location and "outside" not in location:
            return "I leave the Rusty Flagon and follow the road outside, looking for fresh tracks, bridge signs, or the next bandit lead."
        if "bandit" in objective_blob or _quest_status(context, "quest:bandit_road") == "active":
            if "prepare" in objective_blob:
                return "I check my supplies and ask who travels the road before dawn before pursuing the bandit trail."
            return "I inspect the road outside the tavern for tracks, ambush signs, wagon ruts, black cord, or bridge markings."
        return "I inspect the road outside the tavern for tracks, ambush signs, wagon ruts, black cord, or bridge markings."

    if "bandit" in objective_blob or "road" in objective_blob or "bandit" in lower_original:
        return "I leave the tavern and follow the bandit road trail, watching for tracks, ambush signs, or anyone connected to the attack."

    if (
        _story_hook_fired(context, "hook:witness:report_to_bran")
        or _dialogue_topic_repeat_count(context, "Bran", "cloaked_traveler") >= 2
    ):
        return _road_progression_action(context, original_action)

    if "report" in objective_blob and "witness" in objective_blob:
        return "I report to Bran that the cloaked traveler trail points toward the road and ask what danger this confirms."

    if "witness" in objective_blob or "witness" in lower_original or "cloaked" in lower_original:
        if "inspect" in lower_original or "physical clue" in lower_original:
            return "I inspect the tavern side door and nearby street for mud, torn cloth, boot prints, or signs of a hurried exit."
        if "travel" in lower_original or "location" in lower_original or "follow" in lower_original:
            return "I leave the Rusty Flagon and follow the road outside, looking for fresh tracks or the cloaked traveler."
        return f"I ask {npc} where the cloaked traveler went after leaving by the side door."

    suggested = suggested_executable_action(context)
    if suggested:
        return suggested

    generic_affordances = build_objective_affordances_for_state(context, limit=6)
    for row in generic_affordances:
        command = _safe_str(_safe_dict(row).get("command")).strip()
        if (
            command
            and not is_meta_or_vague_action(command)
            and not is_repeated_affordance_action(command, context)
        ):
            return command

    if is_meta_or_vague_action(original_action):
        quests = _safe_dict(_safe_dict(context.get("quest_progress")).get("quests"))
        completed_count = sum(
            1
            for quest in quests.values()
            if _safe_dict(quest).get("completed") or _safe_str(_safe_dict(quest).get("status")) == "completed"
        )
        active_count = sum(
            1
            for quest in quests.values()
            if _safe_str(_safe_dict(quest).get("status")) == "active" and not _safe_dict(quest).get("completed")
        )
        if completed_count > 0 and active_count <= 0:
            return (
                "I investigate the most recent unresolved lead from my last discovery, "
                "checking nearby people, places, tracks, objects, and rumors for the next concrete danger."
            )
        return (
            "I ask a nearby NPC about urgent trouble, unresolved rumors, missing people, "
            "dangerous places, or work that needs immediate action."
        )

    return f"I ask {npc} for one specific fact about the strongest lead, then immediately act on that answer."


def repair_action_if_needed(action: str, context: Dict[str, Any], transcript: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    context = _safe_dict(context)
    original = _safe_str(action).strip()
    normalized = normalize_command_label_action(original)
    if normalized and normalized != original and not is_meta_or_vague_action(normalized):
        return {
            "changed": True,
            "action": normalized,
            "original_action": original,
            "reason": "command_label_normalized_to_first_person_executable_command",
        }
    action = normalized.strip()
    lower_action = action.lower()
    used_explicit_transcript = transcript is not None
    transcript = transcript if transcript is not None else _safe_list(context.get("recent_turns"))
    handoff_action = _handoff_action_from_committed_context(context)

    if handoff_action and (
        is_meta_or_vague_action(original)
        or is_repeated_affordance_action(original, transcript)
        or "review my quest log" in original.lower()
        or "road outside the tavern" in original.lower()
    ):
        return {
            "changed": handoff_action != original,
            "action": handoff_action,
            "original_action": original,
            "reason": "committed_handoff_quest_priority_repair",
        }

    if transcript and is_repeated_affordance_action(action, transcript):
        repaired = choose_rotated_affordance(context, action)
        reason = (
            "repeated_affordance_action_repaired_by_semantic_rotation"
            if used_explicit_transcript
            else "repeated_affordance_action_repaired_to_alternate_objective_affordance"
        )
        if not repaired:
            repaired = executable_action_for_context(context, action)
            reason = "repeated_affordance_action_repaired_by_semantic_rotation"
        return {
            "changed": repaired != action,
            "action": repaired,
            "original_action": original,
            "reason": reason,
        }
    if _post_witness_road_transition_active(context) and _post_transition_forbidden_bran_or_witness_action(action):
        if _has_active_committed_handoff_quest(context):
            handoff_action = _handoff_action_from_committed_context(context)
            if handoff_action:
                return {
                    "changed": handoff_action != original,
                    "action": handoff_action,
                    "original_action": original,
                    "reason": "committed_handoff_quest_priority_repair",
                }
        repaired = _road_progression_action(context, action)
        return {
            "changed": repaired != action,
            "action": repaired,
            "original_action": original,
            "reason": "post_transition_bran_witness_action_repaired_to_road_progression",
        }
    if _quest_completed(context, "quest:witness_search") and any(
        phrase in lower_action
        for phrase in (
            "cloaked traveler",
            "cloak markings",
            "where the cloaked traveler went",
            "report to bran",
            "witness search",
            "side door",
            "ask bran",
            "bran where",
        )
    ):
        if _has_active_committed_handoff_quest(context):
            handoff_action = _handoff_action_from_committed_context(context)
            if handoff_action:
                return {
                    "changed": handoff_action != original,
                    "action": handoff_action,
                    "original_action": original,
                    "reason": "committed_handoff_quest_priority_repair",
                }
        repaired = executable_action_for_context(context, action)
        return {
            "changed": repaired != action,
            "action": repaired,
            "original_action": original,
            "reason": "completed_witness_search_action_repaired_to_bandit_road_progression",
        }
    if not action or is_meta_or_vague_action(action):
        repaired = executable_action_for_context(context, action or original)
        return {
            "changed": repaired != action,
            "action": repaired,
            "original_action": original,
            "reason": "meta_or_vague_action_repaired_to_executable_command",
        }
    lower = action.lower()
    if (
        "report to bran" in lower
        and "trail points toward the road" in lower
        and (
            _story_hook_fired(context, "hook:witness:report_to_bran")
            or _dialogue_topic_repeat_count(context, "Bran", "cloaked_traveler") >= 2
        )
    ):
        repaired = _road_progression_action(context, action)
        return {
            "changed": True,
            "action": repaired,
            "original_action": original,
            "reason": "repeated_completed_report_repaired_to_next_lead",
        }
    if "stop repeating" in lower_action:
        repaired = _road_progression_action(context, action)
        return {
            "changed": repaired != action,
            "action": repaired,
            "original_action": original,
            "reason": "stop_repeating_meta_action_repaired_to_concrete_road_action",
        }
    return {
        "changed": False,
        "action": action,
        "original_action": original,
        "reason": "",
    }