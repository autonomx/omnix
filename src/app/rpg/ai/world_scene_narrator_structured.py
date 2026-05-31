"""Split helpers for RPG world scene narration."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405
from app.rpg.ai.world_scene_narrator_common import *
from app.rpg.ai.world_scene_narrator_payloads import *

def _build_scene_summary(scene: Dict[str, Any], llm_narrative: str) -> str:
    scene = _safe_dict(scene)
    title = _safe_str(scene.get("title")).strip()
    location_name = _first_nonempty(
        scene.get("location_name"),
        scene.get("location_id"),
        scene.get("scene_id"),
    )
    summary = _safe_str(scene.get("summary")).strip()

    if summary:
        if title:
            return f"You are in {title}. {summary}"
        return summary

    llm_lines = _extract_text_lines(llm_narrative)
    if llm_lines:
        return llm_lines[0]

    if title and location_name:
        return f"You are in {title} at {location_name}."
    if title:
        return f"You are in {title}."
    if location_name:
        return f"You are at {location_name}."
    return "The scene settles around you."


def _build_combat_facts_block(narration_context: Dict[str, Any]) -> str:
    combat_result = _safe_dict(narration_context.get("combat_result"))
    npc_combat_result = _safe_dict(narration_context.get("npc_combat_result"))
    combat_state = _safe_dict(narration_context.get("combat_state"))
    if not combat_result and not combat_state and not npc_combat_result:
        return "- none"

    parts = []
    if combat_state:
        parts.append(f'state={_safe_str(combat_state.get("phase") or "idle")}')
    if combat_result:
        parts.append(f'hit={bool(combat_result.get("hit"))}')
        parts.append(f'damage={int(combat_result.get("damage_total", 0) or 0)}')
        parts.append(f'target_downed={bool(combat_result.get("target_downed"))}')
    if npc_combat_result:
        parts.append(f'npc_counterattack_hit={bool(npc_combat_result.get("hit"))}')
        parts.append(f'npc_counterattack_damage={int(npc_combat_result.get("damage_total", 0) or 0)}')
    return ", ".join(parts) if parts else "- none"


def _build_action_result_line(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    combat_result = _safe_dict(narration_context.get("combat_result"))
    if combat_result:
        hit = bool(combat_result.get("hit"))
        damage_total = int(combat_result.get("damage_total", 0) or 0)
        target_downed = bool(combat_result.get("target_downed"))
        target_name = _safe_str(combat_result.get("target_name") or _safe_dict(narration_context.get("resolved_result")).get("target_name")).strip() or "the target"
        if not hit:
            return f"You miss {target_name}."
        if target_downed:
            return f"You strike {target_name}, dealing {damage_total} damage and knocking them down."
        return f"You hit {target_name}, dealing {damage_total} damage."

    resolved = _safe_dict(narration_context.get("resolved_result"))
    service_result = _service_result_from_context(narration_context)
    if service_result.get("matched"):
        grounded_service_action = _service_grounded_action_result(narration_context)
        if grounded_service_action:
            return grounded_service_action

    combat = _safe_dict(resolved.get("combat_result"))
    action_type = _safe_str(narration_context.get("action_type")).strip()
    action_label = _titleize_action(action_type)

    outcome = _safe_str(combat.get("outcome")).strip().lower()
    target_name = _first_nonempty(
        combat.get("target_name"),
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("target_id"),
    )
    damage = int(combat.get("damage", resolved.get("damage", 0)) or 0)

    if outcome in ("hit", "crit", "graze", "miss"):
        if outcome == "miss":
            if target_name:
                return f"**{action_label}:** You miss **{target_name}**."
            return f"**{action_label}:** You miss."
        if target_name:
            return f"**{action_label}:** {outcome.title()} on **{target_name}** for **{damage} damage**."
        return f"**{action_label}:** {outcome.title()} for **{damage} damage**."

    if resolved.get("ok") is False:
        message = _first_nonempty(resolved.get("message"), resolved.get("reason"))
        if message:
            return f"**{action_label}:** {message}"
        return f"**{action_label}:** The attempt fails."

    message = _first_nonempty(
        resolved.get("message"),
        resolved.get("summary"),
        resolved.get("result_text"),
    )
    if message:
        return f"**{action_label}:** {message}"

    return ""


def _pick_npc_reply_text(llm_narrative: str) -> str:
    """Extract NPC dialogue from LLM narrative text."""
    # Look for quoted text or dialogue patterns
    import re
    quotes = re.findall(r'"([^"]*)"', _safe_str(llm_narrative))
    if quotes:
        return quotes[0]
    # Look for dialogue after colons
    dialogue_match = re.search(r':\s*([^.!?]+[.!?])', _safe_str(llm_narrative))
    if dialogue_match:
        return dialogue_match.group(1).strip()
    return ""


def _build_npc_reply_block(scene: Dict[str, Any], narration_context: Dict[str, Any], llm_narrative: str) -> str:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))

    reply = _first_nonempty(
        resolved.get("npc_reply"),
        resolved.get("reply"),
        resolved.get("dialogue"),
        resolved.get("spoken_response"),
    )
    if reply:
        return reply

    target_name = _first_nonempty(
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("target_id"),
    )
    picked = _pick_npc_reply_text(llm_narrative)
    if picked:
        if target_name and target_name.lower() not in picked.lower():
            return f"**{target_name}:** {picked}"
        return picked
    return ""


def _build_rewards_block(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    xp_result = _safe_dict(narration_context.get("xp_result"))
    skill_xp_result = _safe_dict(narration_context.get("skill_xp_result"))
    level_up = _safe_list(narration_context.get("level_up"))
    skill_level_ups = _safe_list(narration_context.get("skill_level_ups"))
    resolved = _safe_dict(narration_context.get("resolved_result"))

    parts: List[str] = []

    player_xp = int(xp_result.get("player_xp", 0) or 0)
    if player_xp > 0:
        parts.append(f"**+{player_xp} XP**")

    awards = _safe_dict(skill_xp_result.get("awards"))
    skill_parts = []
    for skill_id in sorted(awards.keys()):
        amount = int(awards.get(skill_id, 0) or 0)
        if amount > 0:
            skill_parts.append(f"**+{amount} {skill_id} XP**")
    if skill_parts:
        parts.append(", ".join(skill_parts))

    item_name = _first_nonempty(
        resolved.get("item_name"),
        _safe_dict(resolved.get("dropped_item")).get("name"),
        _safe_dict(resolved.get("picked_up_item")).get("name"),
        _safe_dict(resolved.get("item")).get("name"),
    )
    if item_name:
        parts.append(f"**Item:** {item_name}")

    if level_up:
        parts.append("**Level Up!**")

    if skill_level_ups:
        labels = []
        for entry in skill_level_ups:
            entry = _safe_dict(entry)
            skill_id = _first_nonempty(entry.get("skill_id"), entry.get("name"))
            if skill_id:
                labels.append(skill_id)
        if labels:
            parts.append("**Skill Up:** " + ", ".join(labels))

    return " · ".join(parts)


def _collect_emphasis_markers(scene: Dict[str, Any], narration_context: Dict[str, Any], blocks: Dict[str, str]) -> List[str]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    xp_result = _safe_dict(narration_context.get("xp_result"))
    markers: List[str] = []

    for value in [
        scene.get("title"),
        scene.get("location_name"),
        resolved.get("target_name"),
        resolved.get("npc_name"),
        _safe_dict(resolved.get("item")).get("name"),
        _safe_dict(resolved.get("picked_up_item")).get("name"),
        _safe_dict(resolved.get("dropped_item")).get("name"),
    ]:
        text = _safe_str(value).strip()
        if text:
            markers.append(text)

    damage = int(_safe_dict(resolved.get("combat_result")).get("damage", resolved.get("damage", 0)) or 0)
    if damage > 0:
        markers.append(f"{damage} damage")

    player_xp = int(xp_result.get("player_xp", 0) or 0)
    if player_xp > 0:
        markers.append(f"+{player_xp} XP")

    if _safe_list(narration_context.get("level_up")):
        markers.append("Level Up!")

    deduped: List[str] = []
    seen = set()
    for marker in markers:
        key = marker.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(marker)
    return deduped


def apply_narration_emphasis(text: str, emphasis_markers: List[str]) -> str:
    rendered = _safe_str(text)
    for marker in sorted(_safe_list(emphasis_markers), key=len, reverse=True):
        marker = _safe_str(marker).strip()
        if not marker:
            continue
        # Only match standalone text (avoid breaking markdown or double wrapping)
        pattern = rf"(?<!\*)\b{re.escape(marker)}\b(?!\*)"
        rendered = re.sub(pattern, f"**{marker}**", rendered)
    rendered = rendered.replace("****", "**")
    return rendered


def build_structured_narration(scene: Dict[str, Any], narration_context: Dict[str, Any], llm_narrative: str) -> Dict[str, Any]:
    from app.rpg.ai.world_scene_narrator_prompts import (
        _with_scene_response_defaults,
        parse_scene_response,
    )

    parsed = _with_scene_response_defaults(parse_scene_response(llm_narrative))
    npc = _normalize_speaker_block(parsed.get("npc"))
    npc_text = npc.get("text", "")
    action_text = _safe_str(parsed.get("action")).strip() or _build_action_result_line(narration_context)
    rewards_text = _build_rewards_block(narration_context)
    speaker_turns = _build_speaker_turns(parsed)

    blocks = {
        "scene_summary": parsed["narrator"],
        "action_result_line": action_text,
        "npc_reply_block": npc_text,
        "rewards_block": rewards_text,
    }
    emphasis_markers = _collect_emphasis_markers(scene, narration_context, blocks)

    ordered = [
        parsed["narrator"],
        f"**Action:** {action_text}" if action_text else "",
        (
            f"**Reply:** {npc['name'] or 'Character'}: {npc['text']}"
            if npc.get("text")
            else ""
        ),
        f"**Reward:** {rewards_text}" if rewards_text else "",
    ]
    markdown = "\n\n".join(filter(None, ordered))
    markdown = apply_narration_emphasis(markdown, emphasis_markers)

    if len(markdown) > _NARRATION_MAX_MARKDOWN:
        cutoff = markdown[:_NARRATION_MAX_MARKDOWN]
        last_break = cutoff.rfind("\n")
        if last_break > 0:
            cutoff = cutoff[:last_break]
        markdown = cutoff.rstrip() + "..."

    return {
        "scene_summary": apply_narration_emphasis(parsed["narrator"], emphasis_markers),
        "action_result_line": apply_narration_emphasis(action_text, emphasis_markers),
        "npc_reply_block": apply_narration_emphasis(npc_text, emphasis_markers),
        "npc": {
            **npc,
            "text": apply_narration_emphasis(npc_text, emphasis_markers),
        },
        "rewards_block": apply_narration_emphasis(rewards_text, emphasis_markers),
        "emphasis_markers": emphasis_markers,
        "speaker_turns": speaker_turns,
        "markdown": markdown,
    }


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

__all__ = [name for name in globals() if not name.startswith("__")]
