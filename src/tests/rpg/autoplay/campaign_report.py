from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _json(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


SOCIAL_ACTION_WORDS = {
    "ask",
    "talk",
    "tell",
    "say",
    "speak",
    "question",
    "report",
    "explain",
    "share",
    "approach",
    "convince",
    "persuade",
}


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def is_social_player_action(player_action: Any) -> bool:
    text = _norm_text(player_action)
    return any(word in text for word in SOCIAL_ACTION_WORDS)


def is_echoed_narration(*, player_action: Any, narration: Any) -> bool:
    player = _norm_text(player_action)
    narr = _norm_text(narration)
    if not player or not narr:
        return False
    return player == narr or narr in {player.rstrip("."), player + "."}


def _nested_get(value: Dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_turn_ai_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort extraction of the raw/structured narration payload.

    This intentionally reads many shapes because narration output has evolved
    across bundles.
    """
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    result = _safe_dict(turn_result.get("result"))

    candidates = [
        raw_result.get("narration_result"),
        raw_result.get("narration_payload"),
        raw_result.get("narration_json"),
        raw_result.get("structured_narration"),
        raw_result.get("llm_narration"),
        _nested_get(raw_result, "result", "narration_result"),
        _nested_get(raw_result, "result", "narration_payload"),
        _nested_get(raw_result, "session", "runtime_state", "last_narration_payload"),
        _nested_get(raw_result, "session", "runtime_state", "last_structured_narration"),
        manual_summary.get("raw_narration_payload"),
        result.get("narration_payload"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def extract_story_hook_display(row: Dict[str, Any]) -> Dict[str, Any]:
    hook_result = _safe_dict(row.get("story_hook_result"))
    display = _safe_dict(hook_result.get("display"))
    if display:
        return display
    fired_hooks = _safe_list(hook_result.get("fired_hooks"))
    for fired in reversed(fired_hooks):
        display = _safe_dict(_safe_dict(fired).get("display"))
        if display:
            return display
    return {}


def extract_base_response_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(row.get("base_response_payload"))
    if payload:
        return payload
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    payload = _safe_dict(manual_summary.get("base_response_payload"))
    if payload:
        return payload
    return {}


def extract_conversation_beat(row: Dict[str, Any]) -> Dict[str, str]:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    conversation_result = _safe_dict(
        raw_result.get("conversation_result")
        or _nested_get(raw_result, "result", "conversation_result")
    )
    beat = _safe_dict(conversation_result.get("beat"))
    if beat:
        return {
            "speaker": _first_nonempty(beat.get("speaker_name"), beat.get("speaker_id")),
            "line": _safe_str(beat.get("line")),
        }
    beats = _safe_list(conversation_result.get("beats"))
    for item in beats:
        beat = _safe_dict(item)
        if beat.get("line"):
            return {
                "speaker": _first_nonempty(beat.get("speaker_name"), beat.get("speaker_id")),
                "line": _safe_str(beat.get("line")),
            }
    return {}


def classify_dialogue_source(row: Dict[str, Any]) -> str:
    """Classify where the visible NPC dialogue came from."""
    ai_payload = extract_turn_ai_payload(row)
    if _safe_dict(ai_payload.get("npc")).get("line") and _safe_str(ai_payload.get("source")) == "provider_runtime_narration":
        return "real_runtime_provider"

    hook_display = extract_story_hook_display(row)
    if _safe_dict(hook_display.get("npc")).get("line"):
        return "story_hook_display"

    if _safe_dict(ai_payload.get("npc")).get("line"):
        if _safe_str(ai_payload.get("source")) == "deterministic_runtime_narration_fallback":
            return "real_runtime_fallback"
        return "raw_ai_payload"

    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    if _safe_dict(manual_summary.get("raw_npc")).get("line"):
        return "raw_npc"

    if extract_conversation_beat(row).get("line"):
        return "conversation_beat"

    base_response = extract_base_response_payload(row)
    if _safe_dict(base_response.get("npc")).get("line"):
        source = _safe_str(base_response.get("source"))
        if source == "provider_base_runtime_response":
            return "base_runtime_provider"
        return "base_runtime_deterministic"

    return "none"


def extract_dialogue(row: Dict[str, Any]) -> Dict[str, str]:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    ai_payload = extract_turn_ai_payload(row)
    hook_display = extract_story_hook_display(row)
    base_response = extract_base_response_payload(row)
    npc_payload = _safe_dict(ai_payload.get("npc"))
    hook_npc = _safe_dict(hook_display.get("npc"))
    base_npc = _safe_dict(base_response.get("npc"))
    raw_npc = _safe_dict(manual_summary.get("raw_npc"))
    conversation_beat = extract_conversation_beat(row)

    speaker = _first_nonempty(
        npc_payload.get("speaker") if _safe_str(ai_payload.get("source")) == "provider_runtime_narration" else "",
        hook_npc.get("speaker"),
        npc_payload.get("speaker"),
        base_npc.get("speaker"),
        raw_npc.get("speaker"),
        conversation_beat.get("speaker"),
        raw_result.get("npc_speaker"),
        _nested_get(raw_result, "npc", "speaker"),
        _nested_get(raw_result, "result", "npc", "speaker"),
        _nested_get(raw_result, "turn_contract", "npc", "speaker"),
        _nested_get(turn_result, "turn_contract", "npc", "speaker"),
    )
    line = _first_nonempty(
        npc_payload.get("line") if _safe_str(ai_payload.get("source")) == "provider_runtime_narration" else "",
        hook_npc.get("line"),
        npc_payload.get("line"),
        base_npc.get("line"),
        raw_npc.get("line"),
        conversation_beat.get("line"),
        raw_result.get("npc_line"),
        _nested_get(raw_result, "npc", "line"),
        _nested_get(raw_result, "result", "npc", "line"),
        _nested_get(raw_result, "turn_contract", "npc", "line"),
        _nested_get(turn_result, "turn_contract", "npc", "line"),
    )
    return {
        "speaker": speaker,
        "line": line,
    }


def extract_narration(row: Dict[str, Any]) -> str:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    ai_payload = extract_turn_ai_payload(row)
    hook_display = extract_story_hook_display(row)
    base_response = extract_base_response_payload(row)
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    return _first_nonempty(
        ai_payload.get("narration") if _safe_str(ai_payload.get("source")) == "provider_runtime_narration" else "",
        hook_display.get("narration"),
        ai_payload.get("narration"),
        base_response.get("narration"),
        turn_result.get("narration"),
        manual_summary.get("raw_narration"),
        raw_result.get("narration"),
        _nested_get(raw_result, "result", "narration"),
    )


def _latest_state_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in reversed(transcript):
        final_state = _safe_dict(row.get("final_authoritative_state"))
        if final_state:
            return final_state
        turn_result = _safe_dict(row.get("turn_result"))
        state = _safe_dict(turn_result.get("simulation_state"))
        if state:
            return state
    return {}


def _latest_state_source(transcript: List[Dict[str, Any]]) -> str:
    for row in reversed(transcript):
        if _safe_dict(row.get("final_authoritative_state")):
            return "final_authoritative_state"
        turn_result = _safe_dict(row.get("turn_result"))
        if _safe_dict(turn_result.get("simulation_state")):
            return "turn_result.simulation_state"
    return "none"


def _story_arc_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    arcs = _safe_dict(_safe_dict(state.get("story_arc_state")).get("arcs"))
    rows = []
    for arc_id, arc in arcs.items():
        arc = _safe_dict(arc)
        row = dict(arc)
        row.setdefault("arc_id", arc_id)
        rows.append(row)
    return rows


def _milestone_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = _safe_dict(state.get("story_arc_milestone_state"))
    arcs = _safe_dict(root.get("arcs"))
    rows = []
    for arc_id, bucket in arcs.items():
        for milestone in _safe_list(_safe_dict(bucket).get("milestones")):
            if isinstance(milestone, dict):
                row = dict(milestone)
                row.setdefault("arc_id", arc_id)
                rows.append(row)
    return rows


def _journal_entries(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        row
        for row in _safe_list(_safe_dict(state.get("campaign_journal_state")).get("entries"))
        if isinstance(row, dict)
    ]


def _story_events(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        row
        for row in _safe_list(_safe_dict(state.get("story_event_queue_state")).get("queue"))
        if isinstance(row, dict)
    ]


def _npc_rows(state: Dict[str, Any], transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name: Dict[str, Dict[str, Any]] = {}

    # Known state roots vary across bundles; collect likely NPC/profile stores.
    candidate_roots = [
        _safe_dict(state.get("npc_profile_state")).get("profiles"),
        _safe_dict(state.get("npc_evolution_state")).get("npcs"),
        _safe_dict(state.get("social_state")).get("npcs"),
        _safe_dict(state.get("character_state")).get("npcs"),
        state.get("npcs"),
    ]
    for root in candidate_roots:
        if isinstance(root, dict):
            for key, value in root.items():
                value = _safe_dict(value)
                name = _first_nonempty(value.get("name"), value.get("npc_id"), key)
                if name:
                    by_name.setdefault(name, {}).update(value)
                    by_name[name].setdefault("name", name)
        elif isinstance(root, list):
            for value in root:
                value = _safe_dict(value)
                name = _first_nonempty(value.get("name"), value.get("npc_id"))
                if name:
                    by_name.setdefault(name, {}).update(value)
                    by_name[name].setdefault("name", name)

    # Also discover NPCs from dialogue.
    for row in transcript:
        dialogue = extract_dialogue(row)
        speaker = dialogue.get("speaker")
        if speaker:
            by_name.setdefault(speaker, {"name": speaker})
            by_name[speaker]["dialogue_turns"] = int(by_name[speaker].get("dialogue_turns") or 0) + 1

    return sorted(by_name.values(), key=lambda row: str(row.get("name") or ""))


def _player_progression(state: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        state.get("player_state"),
        state.get("character_stats"),
        _safe_dict(state.get("party_state")).get("player"),
        _safe_dict(state.get("runtime")).get("player"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _lore_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    lore = _safe_dict(state.get("lore_state"))
    rows = []
    for key in ("facts", "entries", "locations", "factions", "rumors"):
        value = lore.get(key)
        if isinstance(value, dict):
            for item_id, item in value.items():
                item = _safe_dict(item)
                rows.append({"type": key, "id": item_id, **item})
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    rows.append({"type": key, "id": item.get("id") or idx, **item})
                else:
                    rows.append({"type": key, "id": idx, "text": str(item)})
    return rows


def build_story_so_far_paragraph(model: Dict[str, Any]) -> str:
    timeline = _safe_list(model.get("timeline"))
    milestones = _safe_list(model.get("milestones"))

    completed = [
        row
        for row in milestones
        if _safe_str(row.get("status")) == "completed"
    ]
    active = [
        row
        for row in milestones
        if _safe_str(row.get("status")) not in {"completed", "failed", "cancelled"}
    ]
    completed_titles = [
        _safe_str(row.get("title") or row.get("milestone_id"))
        for row in completed
        if _safe_str(row.get("title") or row.get("milestone_id"))
    ]
    active_titles = [
        _safe_str(row.get("title") or row.get("milestone_id"))
        for row in active
        if _safe_str(row.get("title") or row.get("milestone_id"))
    ]

    if not timeline:
        return "No campaign turns have been recorded yet."

    story_beats = []
    for row in timeline:
        for hook in _safe_list(row.get("fired_hooks")):
            hook = _safe_dict(hook)
            summary = _safe_str(hook.get("story_summary"))
            if summary:
                story_beats.append(summary)

    setup = (
        f"Across {len(timeline)} turns, the campaign followed an investigation that began inside "
        "the Rusty Flagon Tavern and gradually widened toward trouble on the road."
    )
    investigation = ""
    if story_beats:
        investigation = " ".join(story_beats[:6])
    else:
        fallback_beats = _safe_list(_safe_dict(model.get("story_beat_summary")).get("beats"))
        if fallback_beats:
            investigation = "Major story beats were reconstructed from turn activity:"
            for beat in fallback_beats[:5]:
                investigation += f"\n- Turn {beat.get('turn_index')}: {beat.get('summary')}"
        else:
            investigation = "The run recorded player activity, but no major story beats were captured."

    outcome_parts = []
    if completed_titles:
        outcome_parts.append("Completed objectives: " + ", ".join(completed_titles) + ".")
    if active_titles:
        outcome_parts.append("Active unresolved objectives: " + ", ".join(active_titles) + ".")
    if not outcome_parts:
        outcome_parts.append("By the end of the run, the campaign had no active objective, so the director should either declare a chapter boundary or seed the next branch.")

    return "\n\n".join([setup, investigation, " ".join(outcome_parts)])


def build_lore_setting_paragraph(state: Dict[str, Any]) -> str:
    director = _safe_dict(state.get("campaign_director_state"))
    lore_rows = _lore_rows(state)
    premise = _safe_str(director.get("premise"))
    dramatic_question = _safe_str(director.get("dramatic_question"))
    opening_tension = _safe_str(director.get("opening_tension"))
    lore_bits = []
    for row in lore_rows[:4]:
        title = _safe_str(row.get("title") or row.get("name"))
        text = _safe_str(row.get("text") or row.get("description") or row.get("summary"))
        if title and text:
            lore_bits.append(f"{title}: {text}")
        elif text:
            lore_bits.append(text)
        elif title:
            lore_bits.append(title)

    parts = []
    if premise:
        parts.append(premise)
    if opening_tension:
        parts.append(opening_tension)
    if dramatic_question:
        parts.append("The director's dramatic question is: " + dramatic_question)
    if lore_bits:
        parts.append("Setting details: " + " ".join(lore_bits))
    if not parts:
        return "No lore or director setup has been captured yet; the campaign seed should define premise, stakes, and setting context."
    return " ".join(parts)


def build_character_progression_paragraph(state: Dict[str, Any]) -> str:
    player = _player_progression(state)
    npc_progression = _safe_dict(_safe_dict(state.get("npc_progression_state")).get("npcs"))
    parts = []
    if player:
        stats = _safe_dict(player.get("stats"))
        stat_text = ""
        if stats:
            stat_text = (
                " Starting stats were "
                + ", ".join(f"{key} {value}" for key, value in sorted(stats.items()))
                + "."
            )
        parts.append(
            f"The player is level {player.get('level', 1)} with "
            f"{player.get('experience', 0)}/{player.get('experience_to_next_level', 100)} XP toward the next level."
            + stat_text
        )
        log = _safe_list(player.get("progression_log"))
        if log:
            readable = []
            for row in log[-5:]:
                row = _safe_dict(row)
                reason = _safe_str(row.get("summary") or row.get("reason"))
                amount = row.get("amount")
                if reason and amount:
                    readable.append(f"{reason} (+{amount} XP)")
                elif reason:
                    readable.append(reason)
            if readable:
                parts.append("Recent player progression: " + "; ".join(readable) + ".")
    else:
        parts.append("No player progression state is currently captured.")

    if npc_progression:
        npc_bits = []
        for npc_name, npc in npc_progression.items():
            npc = _safe_dict(npc)
            latest_log = _safe_list(npc.get("progression_log"))
            latest_summary = ""
            if latest_log:
                latest_summary = _safe_str(_safe_dict(latest_log[-1]).get("summary"))
            npc_bits.append(
                f"{npc_name} is at growth stage {npc.get('growth_stage', 'unknown')} with trust {npc.get('trust', 0)}"
                + (f" ({latest_summary})" if latest_summary else "")
            )
        parts.append("NPC progression: " + "; ".join(npc_bits) + ".")
    else:
        parts.append("No NPC progression state is currently captured.")
    return " ".join(part for part in parts if part.strip())


def build_player_progression_rows(state: Dict[str, Any]) -> Dict[str, Any]:
    player = _player_progression(state)
    stats = _safe_dict(player.get("stats"))
    log = _safe_list(player.get("progression_log"))
    return {
        "summary_rows": [
            ("Name", player.get("name") or "The Player"),
            ("Level", player.get("level", 1)),
            ("XP", f"{player.get('experience', 0)} / {player.get('experience_to_next_level', 100)}"),
            ("Progress Log Entries", len(log)),
        ],
        "stats_rows": [(str(k).title(), v) for k, v in sorted(stats.items())],
        "recent_progression_rows": [
            [
                row.get("turn_index", ""),
                row.get("type", ""),
                row.get("amount", ""),
                row.get("reason") or row.get("summary") or "",
                f"{row.get('level_before', '')} → {row.get('level_after', '')}" if row.get("level_after") is not None else "",
            ]
            for row in log[-8:]
            if isinstance(row, dict)
        ],
    }


def build_story_arc_report_rows(model: Dict[str, Any]) -> Dict[str, Any]:
    arcs = _safe_list(model.get("story_arcs"))
    milestones = _safe_list(model.get("milestones"))
    by_arc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for milestone in milestones:
        milestone = _safe_dict(milestone)
        by_arc[_safe_str(milestone.get("arc_id"))].append(milestone)
    rows = []
    for arc in arcs:
        arc = _safe_dict(arc)
        arc_id = _safe_str(arc.get("arc_id"))
        arc_milestones = by_arc.get(arc_id, [])
        completed = [m for m in arc_milestones if _safe_str(m.get("status")) == "completed"]
        active = [m for m in arc_milestones if _safe_str(m.get("status")) not in {"completed", "failed", "cancelled"}]
        rows.append(
            {
                "arc_id": arc_id,
                "title": arc.get("title") or arc_id,
                "stage": arc.get("stage"),
                "status": arc.get("status"),
                "pressure": arc.get("pressure", 0),
                "completed_count": len(completed),
                "active_count": len(active),
                "milestones": arc_milestones,
            }
        )
    return {
        "arcs": rows,
        "total_arcs": len(rows),
        "total_milestones": len(milestones),
    }


def build_inventory_rows(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    currency = _safe_dict(snapshot.get("currency"))
    items = _safe_list(snapshot.get("items"))
    return {
        "currency_rows": [[k, v] for k, v in sorted(currency.items())],
        "item_rows": [
            [
                _safe_dict(item).get("name") or _safe_dict(item).get("item_id") or "",
                _safe_dict(item).get("quantity", 1),
                _safe_dict(item).get("type", ""),
                _safe_dict(item).get("description", ""),
            ]
            for item in items
            if isinstance(item, dict)
        ],
    }


def build_location_journey_model(
    *,
    timeline: List[Dict[str, Any]],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    director = _safe_dict(state.get("campaign_director_state"))
    location_rows: Dict[str, Dict[str, Any]] = {}

    def ensure_location(name: str) -> Dict[str, Any]:
        key = name or "Unknown Location"
        location_rows.setdefault(
            key,
            {
                "name": key,
                "turns": [],
                "summary_bits": [],
                "npcs": set(),
                "objectives": set(),
                "events": [],
            },
        )
        return location_rows[key]

    # Seed known setting locations from lore/director.
    ensure_location("The Rusty Flagon Tavern")["summary_bits"].append(
        "The social hub where the witness investigation begins."
    )
    ensure_location("The Bandit Road")["summary_bits"].append(
        "The external danger path revealed after the witness report."
    )

    for row in timeline:
        action = _norm_text(row.get("player_action"))
        if "road" in action or "bandit" in action or "outside" in action:
            loc = ensure_location("The Bandit Road")
        else:
            loc = ensure_location("The Rusty Flagon Tavern")
        loc["turns"].append(row.get("turn_index"))
        narration = _safe_str(row.get("narration"))
        if narration:
            loc["summary_bits"].append(narration)
        npc = _safe_dict(row.get("npc"))
        if npc.get("speaker"):
            loc["npcs"].add(str(npc.get("speaker")))
        for hook in _safe_list(row.get("fired_hooks")):
            hook = _safe_dict(hook)
            if hook.get("story_label"):
                loc["events"].append(hook.get("story_label"))

    for milestone in _milestone_rows(state):
        title = _safe_str(milestone.get("title") or milestone.get("milestone_id"))
        if not title:
            continue
        text = _norm_text(title + " " + _safe_str(milestone.get("objective_text")))
        if "road" in text or "bandit" in text:
            ensure_location("The Bandit Road")["objectives"].add(title)
        else:
            ensure_location("The Rusty Flagon Tavern")["objectives"].add(title)

    locations = []
    for loc in location_rows.values():
        bits = []
        seen_bits = set()
        for bit in loc["summary_bits"]:
            bit = _safe_str(bit)
            if not bit or bit in seen_bits:
                continue
            seen_bits.add(bit)
            bits.append(bit)
            if len(bits) >= 4:
                break
        locations.append(
            {
                "name": loc["name"],
                "turn_range": (
                    f"{min(loc['turns'])}–{max(loc['turns'])}" if loc["turns"] else "setup"
                ),
                "turn_count": len(loc["turns"]),
                "summary": " ".join(bits) if bits else "No summary captured.",
                "npcs": sorted(loc["npcs"]),
                "objectives": sorted(loc["objectives"]),
                "events": loc["events"][:8],
            }
        )
    return {
        "locations": locations,
        "director_context": {
            "premise": director.get("premise"),
            "stakes": director.get("stakes"),
        },
    }


def compute_dialogue_coverage(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_turns = len(timeline)
    social_turns = [row for row in timeline if row.get("social_action")]
    npc_response_turns = [
        row
        for row in timeline
        if _safe_dict(row.get("npc")).get("line")
    ]
    missing_social_turns = [
        row
        for row in social_turns
        if row.get("missing_npc_response")
    ]
    echoed_narration_turns = [
        row
        for row in timeline
        if row.get("echoed_narration")
    ]
    source_counts = Counter(
        _safe_str(row.get("dialogue_source") or "none")
        for row in timeline
    )
    hook_dialogue_turns = [
        row for row in timeline if row.get("dialogue_source") == "story_hook_display"
    ]
    base_dialogue_turns = [
        row
        for row in timeline
        if row.get("dialogue_source")
        in {
            "raw_ai_payload",
            "raw_npc",
            "conversation_beat",
            "real_runtime_provider",
            "real_runtime_fallback",
            "base_runtime_deterministic",
            "base_runtime_provider",
        }
    ]
    return {
        "total_turns": total_turns,
        "social_turn_count": len(social_turns),
        "npc_response_turn_count": len(npc_response_turns),
        "npc_response_rate": (len(npc_response_turns) / total_turns) if total_turns else 0.0,
        "social_turn_missing_npc_response_count": len(missing_social_turns),
        "social_turn_missing_npc_response_rate": (
            len(missing_social_turns) / len(social_turns) if social_turns else 0.0
        ),
        "echoed_narration_turn_count": len(echoed_narration_turns),
        "echoed_narration_rate": (
            len(echoed_narration_turns) / total_turns if total_turns else 0.0
        ),
        "dialogue_source_counts": dict(source_counts),
        "hook_dialogue_turn_count": len(hook_dialogue_turns),
        "base_runtime_dialogue_turn_count": len(base_dialogue_turns),
        "real_runtime_dialogue_turn_count": int(source_counts.get("real_runtime_provider") or 0)
        + int(source_counts.get("real_runtime_fallback") or 0),
        "real_runtime_provider_dialogue_turn_count": int(source_counts.get("real_runtime_provider") or 0),
        "real_runtime_fallback_dialogue_turn_count": int(source_counts.get("real_runtime_fallback") or 0),
        "missing_social_turns": [
            {
                "turn_index": row.get("turn_index"),
                "player_action": row.get("player_action"),
            }
            for row in missing_social_turns[:25]
        ],
        "echoed_narration_turns": [
            {
                "turn_index": row.get("turn_index"),
                "player_action": row.get("player_action"),
                "narration": row.get("narration"),
            }
            for row in echoed_narration_turns[:25]
        ],
    }


def build_chapter_status(state: Dict[str, Any], model_like: Dict[str, Any]) -> Dict[str, Any]:
    director = _safe_dict(state.get("campaign_director_state"))
    milestones = _safe_list(model_like.get("milestones"))
    completed = [
        row for row in milestones if _safe_str(row.get("status")) == "completed"
    ]
    active = [
        row
        for row in milestones
        if _safe_str(row.get("status")) not in {"completed", "failed", "cancelled"}
    ]
    arcs = _story_arc_rows(state)
    current_stage = ""
    if arcs:
        current_stage = _safe_str(arcs[0].get("stage"))
    chapter_complete = bool(completed and not active)
    recommendation = ""
    if chapter_complete:
        recommendation = (
            "The current chapter appears complete. The director should either declare a chapter boundary "
            "or seed a follow-up objective so long autoplay runs do not drift."
        )
    elif active:
        recommendation = "The campaign has active objectives and can continue from the current branch."
    else:
        recommendation = "No active objective was found; the director should seed the next actionable goal."
    return {
        "campaign_title": director.get("campaign_title") or "Untitled Campaign",
        "current_stage": current_stage,
        "completed_objective_count": len(completed),
        "active_objective_count": len(active),
        "completed_objectives": [
            row.get("title") or row.get("milestone_id") for row in completed
        ],
        "active_objectives": [
            row.get("title") or row.get("milestone_id") for row in active
        ],
        "chapter_complete": chapter_complete,
        "recommendation": recommendation,
    }


def compute_runtime_narration_diagnostics(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    provider_present = 0
    provider_attempted = 0
    provider_valid = 0
    provider_repaired = 0
    fallback_used = 0
    provider_errors = Counter()
    provider_original_errors = Counter()
    provider_repair_actions = Counter()
    provider_shapes = Counter()
    selected_methods = Counter()
    retry_count = 0
    attempt_count = 0
    for row in timeline:
        diag = _safe_dict(row.get("runtime_narration_diagnostics"))
        if not diag:
            continue
        if diag.get("provider_present"):
            provider_present += 1
        if diag.get("provider_attempted"):
            provider_attempted += 1
        if diag.get("provider_valid"):
            provider_valid += 1
        if diag.get("provider_repaired"):
            provider_repaired += 1
        if diag.get("fallback_used"):
            fallback_used += 1
        retry_count += int(diag.get("provider_retry_count") or 0)
        attempt_count += int(diag.get("provider_attempt_count") or 0)
        for err in _safe_list(diag.get("provider_errors")):
            provider_errors[str(err)] += 1
        for err in _safe_list(diag.get("provider_original_errors")):
            provider_original_errors[str(err)] += 1
        for action in _safe_list(diag.get("provider_repair_actions")):
            provider_repair_actions[str(action)] += 1
        shape = _safe_dict(diag.get("provider_shape"))
        if shape:
            provider_shapes[json.dumps(shape, sort_keys=True, default=str)] += 1
        call_diag = _safe_dict(diag.get("provider_call_diagnostics"))
        if call_diag.get("selected_method"):
            selected_methods[str(call_diag.get("selected_method"))] += 1
    return {
        "provider_present_turns": provider_present,
        "provider_attempted_turns": provider_attempted,
        "provider_valid_turns": provider_valid,
        "provider_repaired_turns": provider_repaired,
        "provider_attempt_count": attempt_count,
        "provider_retry_count": retry_count,
        "fallback_used_turns": fallback_used,
        "provider_error_counts": dict(provider_errors),
        "provider_original_error_counts": dict(provider_original_errors),
        "provider_repair_action_counts": dict(provider_repair_actions),
        "provider_shape_counts": dict(provider_shapes),
        "provider_selected_method_counts": dict(selected_methods),
    }


def build_campaign_report_model(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    health: Dict[str, Any],
) -> Dict[str, Any]:
    latest_state = _latest_state_from_transcript(transcript)
    latest_state_source = _latest_state_source(transcript)
    initial_state = _initial_state_from_transcript(transcript)
    quality = _safe_dict(metrics.get("progress_quality"))
    turn_count_for_rates = max(1, len(transcript))
    quality.setdefault("weak_progress_rate", float(quality.get("weak_progress_turns") or 0) / turn_count_for_rates)
    quality.setdefault("no_change_rate", float(quality.get("no_change_turns") or 0) / turn_count_for_rates)
    quality.setdefault("churn_only_rate", float(quality.get("churn_only_turns") or 0) / turn_count_for_rates)
    action_diversity = _safe_dict(metrics.get("action_diversity"))
    category_counts = Counter()
    hook_counts = Counter()
    npc_dialogue_counts = Counter()

    timeline = []
    for row in transcript:
        dialogue = extract_dialogue(row)
        narration = extract_narration(row)
        dialogue_source = classify_dialogue_source(row)
        player_action = _safe_str(row.get("player_action"))
        social_action = is_social_player_action(player_action)
        missing_npc_response = bool(social_action and not dialogue.get("line"))
        echoed_narration = is_echoed_narration(
            player_action=player_action,
            narration=narration,
        )
        progress_delta = _safe_dict(row.get("progress_delta"))
        progress_quality = _safe_dict(row.get("progress_quality"))
        hook_result = _safe_dict(row.get("story_hook_result"))
        fired_hooks = _safe_list(hook_result.get("fired_hooks"))
        for category in _safe_list(progress_delta.get("categories")):
            category_counts[str(category)] += 1
        for hook in fired_hooks:
            hook = _safe_dict(hook)
            if hook.get("hook_id"):
                hook_counts[str(hook.get("hook_id"))] += 1
        if dialogue.get("speaker"):
            npc_dialogue_counts[dialogue["speaker"]] += 1
        timeline.append(
            {
                "turn_index": row.get("turn_index"),
                "player_action": player_action,
                "narration": narration,
                "npc": dialogue,
                "dialogue_source": dialogue_source,
                "social_action": social_action,
                "missing_npc_response": missing_npc_response,
                "echoed_narration": echoed_narration,
                "progress_delta": progress_delta,
                "progress_quality": progress_quality,
                "fired_hooks": fired_hooks,
                "state_preservation_debug": row.get("state_preservation_debug") or {},
                "performance": row.get("performance") or {},
                "base_response_payload": row.get("base_response_payload") or {},
                "runtime_narration_diagnostics": _safe_dict(
                    _safe_dict(extract_turn_ai_payload(row)).get("runtime_narration_diagnostics")
                ),
            }
        )

    dialogue_coverage = compute_dialogue_coverage(timeline)
    runtime_narration_diagnostics = compute_runtime_narration_diagnostics(timeline)

    shortcomings = []
    if float(quality.get("meaningful_progress_rate") or 0.0) < 0.15 and transcript:
        shortcomings.append("Low meaningful progress rate; story may be stalling or progression hooks may be too sparse.")
    if int(quality.get("weak_progress_turns") or 0) > int(quality.get("meaningful_turns") or 0):
        shortcomings.append("Weak/journal-only progress exceeds meaningful progress; journal churn may be too generous.")
    if int(metrics.get("checkpoint_failure_count") or 0) > 0:
        shortcomings.append("One or more save/load checkpoints failed.")
    if int(metrics.get("state_bound_warning_count") or 0) > 0:
        shortcomings.append("State bounds warnings occurred; long-run state may be growing unsafely.")
    if not hook_counts:
        shortcomings.append("No story hooks fired; deterministic story progression may be missing.")
    if not npc_dialogue_counts:
        shortcomings.append("No NPC dialogue extracted; narration payload may not expose speaker/line fields.")
    if int(dialogue_coverage.get("social_turn_missing_npc_response_count") or 0) > 0:
        shortcomings.append(
            f"{dialogue_coverage.get('social_turn_missing_npc_response_count')} social turns had no extracted NPC response; "
            "base-runtime dialogue coverage is incomplete."
        )
    if int(dialogue_coverage.get("echoed_narration_turn_count") or 0) > 0:
        shortcomings.append(
            f"{dialogue_coverage.get('echoed_narration_turn_count')} turns appear to echo the player action as narration; "
            "the narration runtime may be falling back instead of generating scene response text."
        )
    if (
        int(dialogue_coverage.get("hook_dialogue_turn_count") or 0) > 0
        and int(dialogue_coverage.get("base_runtime_dialogue_turn_count") or 0) == 0
    ):
        shortcomings.append(
            "All visible NPC dialogue came from story-hook display payloads; normal non-hook dialogue still needs runtime support."
        )
    source_counts = _safe_dict(dialogue_coverage.get("dialogue_source_counts"))
    deterministic_count = int(source_counts.get("base_runtime_deterministic") or 0)
    provider_count = int(source_counts.get("base_runtime_provider") or 0)
    if deterministic_count > 0 and provider_count == 0:
        shortcomings.append(
            "Some non-hook dialogue is supplied by fallback narration rather than valid provider narration; provider-backed runtime narration should be validated next."
        )
    if int(runtime_narration_diagnostics.get("provider_valid_turns") or 0) == 0:
        shortcomings.append(
            "Real runtime narration used deterministic fallback for all turns; provider-backed runtime narration is not active or not producing valid contract JSON."
        )
    elif int(runtime_narration_diagnostics.get("provider_repaired_turns") or 0) > 0:
        shortcomings.append(
            f"Provider runtime narration required contract repair on {runtime_narration_diagnostics.get('provider_repaired_turns')} turns; "
            "provider prompt/quality gates should be tightened."
        )
    if int(metrics.get("player_agent_exception_count") or 0) > 0:
        shortcomings.append(
            f"Player-agent exceptions occurred on {metrics.get('player_agent_exception_count')} turns; "
            "this run may reflect fallback action logic rather than real LLM player behavior."
        )
    if float(metrics.get("fallback_player_action_rate") or 0.0) >= 0.5:
        shortcomings.append(
            f"Fallback player action rate was {metrics.get('fallback_player_action_rate')}; "
            "storytelling evaluation should be treated cautiously until the LLM player-agent path is fixed."
        )

    model = {
        "summary": summary,
        "metrics": metrics,
        "health": health,
        "latest_state": latest_state,
        "latest_state_source": latest_state_source,
        "initial_state": initial_state,
        "inventory_start": _inventory_snapshot(initial_state),
        "inventory_end": _inventory_snapshot(latest_state),
        "timeline": timeline,
        "story_arcs": _story_arc_rows(latest_state),
        "milestones": _milestone_rows(latest_state),
        "journal_entries": _journal_entries(latest_state),
        "story_events": _story_events(latest_state),
        "npcs": _npc_rows(latest_state, transcript),
        "player_progression": _player_progression(latest_state),
        "lore": _lore_rows(latest_state),
        "category_counts": dict(category_counts),
        "hook_counts": dict(hook_counts),
        "npc_dialogue_counts": dict(npc_dialogue_counts),
        "action_diversity": action_diversity,
        "dialogue_coverage": dialogue_coverage,
        "runtime_narration_diagnostics": runtime_narration_diagnostics,
        "background_jobs": _safe_dict(metrics.get("background_jobs")),
        "provider_trace_summary": _safe_dict(metrics.get("provider_trace_summary")),
        "manual_harness_trace_summary": _safe_dict(metrics.get("manual_harness_trace_summary")),
        "turn_perf_trace_summary": _safe_dict(metrics.get("turn_perf_trace_summary")),
        "player_agent_trace_summary": _safe_dict(metrics.get("player_agent_trace_summary")),
        "deferred_narration_trace_summary": _safe_dict(metrics.get("deferred_narration_trace_summary")),
        "deferred_advisory_trace_summary": _safe_dict(metrics.get("deferred_advisory_trace_summary")),
        "performance_budget_summary": _safe_dict(metrics.get("performance_budget_summary")),
        "background_prompt_budget_summary": _safe_dict(metrics.get("background_prompt_budget_summary")),
        "combined_quality_shape_summary": _safe_dict(metrics.get("combined_quality_shape_summary")),
        "player_agent_prompt_budget_summary": _safe_dict(summary.get("player_agent_prompt_budget_summary")),
        "player_agent_cache_summary": _safe_dict(summary.get("player_agent_cache_summary")),
        "deferred_advisory_promotion_summary": _safe_dict(
            summary.get("deferred_advisory_promotion_summary")
            or metrics.get("deferred_advisory_promotion_summary")
        ),
        "npc_evolution_summary": _safe_dict(summary.get("npc_evolution_summary") or metrics.get("npc_evolution_summary")),
        "npc_evolution_profile_persistence_summary": _safe_dict(
            summary.get("npc_evolution_profile_persistence_summary")
            or metrics.get("npc_evolution_profile_persistence_summary")
        ),
        "npc_profile_load_summary": _safe_dict(
            summary.get("npc_profile_load_summary")
            or metrics.get("npc_profile_load_summary")
        ),
        "profile_grounded_output_summary": _safe_dict(
            summary.get("profile_grounded_output_summary")
            or metrics.get("profile_grounded_output_summary")
        ),
        "npc_arc_progression_summary": _safe_dict(
            summary.get("npc_arc_progression_summary")
            or metrics.get("npc_arc_progression_summary")
        ),
        "npc_evolution_report_summary": _safe_dict(
            summary.get("npc_evolution_report_summary")
            or metrics.get("npc_evolution_report_summary")
        ),
        "quest_progress_summary": _safe_dict(
            summary.get("quest_progress_summary")
            or metrics.get("quest_progress_summary")
        ),
        "story_beat_summary": _safe_dict(
            summary.get("story_beat_summary")
            or metrics.get("story_beat_summary")
        ),
        "manual_turn_error_summary": _safe_dict(
            summary.get("manual_turn_error_summary")
            or metrics.get("manual_turn_error_summary")
        ),
        "console_log_summary": _safe_dict(
            summary.get("console_log_summary")
            or metrics.get("console_log_summary")
        ),
        "campaign_calendar_summary": _safe_dict(
            summary.get("campaign_calendar_summary")
            or metrics.get("campaign_calendar_summary")
        ),
        "player_journal_summary": _safe_dict(
            summary.get("player_journal_summary")
            or metrics.get("player_journal_summary")
        ),
        "promotion_target_grounding_summary": _safe_dict(
            summary.get("promotion_target_grounding_summary")
            or metrics.get("promotion_target_grounding_summary")
        ),
        "quality_gate_summary": _safe_dict(summary.get("quality_gate_summary")),
        "shortcomings": shortcomings,
    }
    model["story_so_far_paragraph"] = build_story_so_far_paragraph(model)
    model["lore_setting_paragraph"] = build_lore_setting_paragraph(latest_state)
    model["character_progression_paragraph"] = build_character_progression_paragraph(latest_state)
    model["chapter_status"] = build_chapter_status(latest_state, model)
    model["player_progression_view"] = build_player_progression_rows(latest_state)
    model["story_arc_view"] = build_story_arc_report_rows(model)
    model["inventory_start_view"] = build_inventory_rows(_safe_dict(model["inventory_start"]))
    model["inventory_end_view"] = build_inventory_rows(_safe_dict(model["inventory_end"]))
    model["location_journey"] = build_location_journey_model(
        timeline=timeline,
        state=latest_state,
    )
    model["pm_summary"] = build_pm_report_summary(model)
    return model


def _render_badge(text: Any, cls: str = "") -> str:
    return f'<span class="badge {html.escape(cls)}">{_esc(str(text))}</span>'


def _render_paragraphs(text: Any) -> str:
    chunks = [chunk.strip() for chunk in str(text or "").split("\n\n") if chunk.strip()]
    if not chunks:
        return '<p class="muted">No narrative summary available.</p>'
    return "\n".join(f"<p>{_esc(chunk)}</p>" for chunk in chunks)


def _render_table(headers: List[str], rows: List[List[Any]]) -> str:
    if not rows:
        return '<p class="muted">No data captured.</p>'
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _status_class(value: Any) -> str:
    text = _safe_str(value).lower()
    if text in {"pass", "passed", "good", "ok", "true", "healthy"}:
        return "good"
    if text in {"warn", "warning", "partial", "caution"}:
        return "warn"
    if text in {"fail", "failed", "bad", "false", "error"}:
        return "bad"
    return ""


def _render_json_details(title: str, value: Any, *, open_by_default: bool = False) -> str:
    open_attr = " open" if open_by_default else ""
    return (
        f"<details class=\"tech-details\"{open_attr}>"
        f"<summary>{_esc(title)}</summary>"
        f"<pre>{_json(value)}</pre>"
        f"</details>"
    )


def _render_console_log_summary(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    if not summary:
        return """
        <section id="console-log">
          <h2>Console Log</h2>
          <p>No captured console log was found for this run.</p>
        </section>
        """
    turn_errors = summary.get("turn_errors") if isinstance(summary.get("turn_errors"), list) else []
    errors = summary.get("errors") if isinstance(summary.get("errors"), list) else []
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    tail = summary.get("tail") if isinstance(summary.get("tail"), list) else []

    turn_error_html = "".join(f"<li>{_esc(str(line))}</li>" for line in turn_errors[:20])
    error_html = "".join(f"<li>{_esc(str(line))}</li>" for line in errors[:20])
    warning_html = "".join(f"<li>{_esc(str(line))}</li>" for line in warnings[:20])
    tail_text = "\n".join(str(line) for line in tail[-80:])
    return f"""
    <section id="console-log">
      <h2>Console Log</h2>
      <p><strong>Captured file:</strong> {_esc(str(summary.get("path") or "console-log.txt"))}</p>
      <p>
        Lines: {_esc(str(summary.get("line_count") or 0))} ·
        Errors: {_esc(str(summary.get("error_count") or 0))} ·
        Turn errors: {_esc(str(summary.get("turn_error_count") or 0))} ·
        Warnings: {_esc(str(summary.get("warning_count") or 0))}
      </p>
      <h3>Turn Errors</h3>
      <ul>{turn_error_html or "<li>None.</li>"}</ul>
      <h3>Errors</h3>
      <ul>{error_html or "<li>None.</li>"}</ul>
      <h3>Warnings</h3>
      <ul>{warning_html or "<li>None.</li>"}</ul>
      <details>
        <summary>Console tail</summary>
        <pre>{_esc(tail_text)}</pre>
      </details>
    </section>
    """


def _render_npc_evolution_cards(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    cards = summary.get("cards") if isinstance(summary.get("cards"), list) else []
    if not cards:
        return '<section id="npc-evolution"><h2>NPC Evolution</h2><p>No NPC evolution arcs found yet.</p></section>'
    rows = []
    for card_any in cards:
        card = _safe_dict(card_any)
        axes = _safe_dict(card.get("axes"))
        axes_html = "".join(
            f"<tr><td>{_esc(str(axis))}</td><td>{_esc(str(value))}</td></tr>"
            for axis, value in sorted(axes.items())
        )
        memories = "".join(
            f"<li>{_esc(str(_safe_dict(item).get('summary') or item))}</li>"
            for item in (card.get("memories") if isinstance(card.get("memories"), list) else [])[-5:]
        )
        hooks = "".join(
            f"<li>{_esc(str(_safe_dict(item).get('summary') or item))}</li>"
            for item in (card.get("future_hooks") if isinstance(card.get("future_hooks"), list) else [])[-5:]
        )
        milestones = "".join(
            "<li>"
            + _esc(
                f"{_safe_dict(item).get('from', '')} → {_safe_dict(item).get('to', '')}"
                f" ({_safe_dict(item).get('reason', '')})"
            )
            + "</li>"
            for item in (card.get("milestones") if isinstance(card.get("milestones"), list) else [])[-5:]
        )
        rows.append(
            f"""
            <article class="npc-card">
              <h3>{_esc(str(card.get('npc_id') or 'Unknown NPC'))}</h3>
              <p><strong>Arc stage:</strong> {_esc(str(card.get('arc_stage') or 'stable'))}</p>
              <p><strong>Signals:</strong> {_esc(str(card.get('signal_count') or 0))}</p>
              <p><strong>Profile:</strong> {_esc(str(card.get('profile_path') or 'not loaded'))}</p>
              <h4>Axes</h4>
              <table><tbody>{axes_html}</tbody></table>
              <h4>Recent Memories</h4>
              <ul>{memories or '<li>None yet.</li>'}</ul>
              <h4>Future Hooks</h4>
              <ul>{hooks or '<li>None yet.</li>'}</ul>
              <h4>Milestones</h4>
              <ul>{milestones or '<li>No stage changes yet.</li>'}</ul>
            </article>
            """
        )
    return f"""
    <section id="npc-evolution">
      <h2>NPC Evolution</h2>
      <p>{_esc(str(summary.get('npc_count') or len(cards)))} NPC profile(s) tracked.</p>
      <div class="npc-card-grid">{''.join(rows)}</div>
    </section>
    """


def _render_quest_progress(summary: Dict[str, Any]) -> str:
    summary = _safe_dict(summary)
    quests = summary.get("quests") if isinstance(summary.get("quests"), list) else []
    if not quests:
        return '<section id="quest-progress"><h2>Quest Progress</h2><p>No quest records found in this run.</p></section>'
    rows = "".join(
        "<tr>"
        f"<td>{_esc(str(_safe_dict(quest).get('title') or _safe_dict(quest).get('quest_id')))}</td>"
        f"<td>{_esc(str(_safe_dict(quest).get('status') or 'unknown'))}</td>"
        f"<td>{_esc(str(_safe_dict(quest).get('progress') or ''))}</td>"
        f"<td>{_esc(str(_safe_dict(quest).get('giver') or ''))}</td>"
        f"<td>{_esc(str(_safe_dict(quest).get('location') or ''))}</td>"
        "</tr>"
        for quest in quests
    )
    return f"""
    <section id="quest-progress">
      <h2>Quest Progress</h2>
      <p>Active: {_esc(str(summary.get('active_count') or 0))} ·
         Completed: {_esc(str(summary.get('completed_count') or 0))} ·
         Failed: {_esc(str(summary.get('failed_count') or 0))} ·
         Unknown: {_esc(str(summary.get('unknown_count') or 0))}</p>
      <table>
        <thead><tr><th>Quest</th><th>Status</th><th>Progress</th><th>Giver</th><th>Location</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _render_calendar_and_journal(calendar: Dict[str, Any], journal: Dict[str, Any]) -> str:
    calendar = _safe_dict(calendar)
    journal = _safe_dict(journal)
    end = _safe_dict(calendar.get("end"))
    entries = journal.get("entries") if isinstance(journal.get("entries"), list) else []
    entry_html = "".join(
        f"""
        <article class="journal-entry">
          <h4>{_esc(str(_safe_dict(entry).get('entry_id') or 'Journal Entry'))}</h4>
          <p><strong>Turns:</strong> {_esc(str(_safe_dict(entry).get('start_turn')))}–{_esc(str(_safe_dict(entry).get('end_turn')))}</p>
          <p>{_esc(str(_safe_dict(entry).get('text') or ''))}</p>
        </article>
        """
        for entry in entries[-8:]
    )
    return f"""
    <section id="campaign-journal">
      <h2>Campaign Calendar & Player Journal</h2>
      <p><strong>Current campaign time:</strong>
        Year {_esc(str(end.get('year') or ''))},
        {_esc(str(end.get('season') or ''))},
        month {_esc(str(end.get('month') or ''))},
        day {_esc(str(end.get('day') or ''))},
        {_esc(str(end.get('time_label') or ''))}
        ({_esc(str(end.get('day_phase') or ''))})
      </p>
      <p><strong>Turns tracked:</strong> {_esc(str(calendar.get('turns_tracked') or 0))};
         <strong>Journal entries:</strong> {_esc(str(journal.get('entry_count') or 0))}</p>
      <div>{entry_html or '<p>No journal entries yet.</p>'}</div>
    </section>
    """


def _render_report_quick_links(model: Dict[str, Any]) -> str:
    journal = _safe_dict(model.get("player_journal_summary"))
    quests = _safe_dict(model.get("quest_progress_summary"))
    npc_evolution = _safe_dict(model.get("npc_evolution_report_summary"))
    journal_count = int(journal.get("entry_count") or 0)
    quest_count = int(quests.get("quest_count") or 0)
    npc_count = int(npc_evolution.get("npc_count") or 0)
    return f"""
    <section class="report-quick-links">
      <h2>Report Highlights</h2>
      <nav>
        <a href="#campaign-journal">Campaign Journal ({_esc(str(journal_count))})</a>
        <a href="#quest-progress">Quest Progress ({_esc(str(quest_count))})</a>
        <a href="#npc-evolution">NPC Evolution ({_esc(str(npc_count))})</a>
      </nav>
    </section>
    """


def _pct(value: Any) -> float:
    try:
        value = float(value)
    except Exception:
        return 0.0
    if value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _seconds_from_ms(value: Any) -> str:
    try:
        return f"{float(value) / 1000.0:.2f}s"
    except Exception:
        return "0.00s"


def _number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0"


def _render_bar(label: str, value: Any, *, max_value: float | None = None, suffix: str = "") -> str:
    try:
        raw = float(value)
    except Exception:
        raw = 0.0
    width = _pct(raw if max_value is None else (raw / max_value if max_value else 0.0))
    display = f"{raw:.2f}{suffix}" if isinstance(raw, float) else f"{raw}{suffix}"
    return (
        '<div class="bar-row">'
        f'<div class="bar-label">{_esc(label)}</div>'
        '<div class="bar-track">'
        f'<div class="bar-fill" style="width:{width:.1f}%"></div>'
        '</div>'
        f'<div class="bar-value">{_esc(display)}</div>'
        '</div>'
    )


def _render_progress_bar(label: str, rate: Any) -> str:
    percent = _pct(rate)
    return (
        '<div class="bar-row">'
        f'<div class="bar-label">{_esc(label)}</div>'
        '<div class="bar-track">'
        f'<div class="bar-fill" style="width:{percent:.1f}%"></div>'
        '</div>'
        f'<div class="bar-value">{percent:.1f}%</div>'
        '</div>'
    )


def _render_key_value_table(rows: List[tuple[str, Any]]) -> str:
    return (
        '<table class="kv-table"><tbody>'
        + ''.join(f'<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>' for k, v in rows)
        + '</tbody></table>'
    )


def _render_chapter_status_cards(chapter_status: Dict[str, Any]) -> str:
    active = _safe_list(chapter_status.get("active_objectives"))
    completed = _safe_list(chapter_status.get("completed_objectives"))
    active_rows = [[title] for title in active]
    completed_rows = [[title] for title in completed]
    return f'''
    <div class="grid">
      <div class="metric"><div class="value">{_esc(chapter_status.get("campaign_title") or "Untitled")}</div><div>Campaign Title</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("current_stage") or "unknown")}</div><div>Current Stage</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("chapter_complete"))}</div><div>Chapter Complete</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("active_objective_count"))}</div><div>Active Objectives</div></div>
      <div class="metric"><div class="value">{_esc(chapter_status.get("completed_objective_count"))}</div><div>Completed Objectives</div></div>
    </div>
    <p class="section-lede"><strong>Recommendation:</strong> {_esc(chapter_status.get("recommendation"))}</p>
    <div class="two-col">
      <div>
        <h3>Active Objectives</h3>
        {_render_table(["Objective"], active_rows)}
      </div>
      <div>
        <h3>Completed Objectives</h3>
        {_render_table(["Objective"], completed_rows)}
      </div>
    </div>
    {_render_json_details("Chapter status JSON", chapter_status)}
    '''


def _inventory_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        state.get("inventory_state"),
        state.get("player_inventory"),
        _safe_dict(state.get("player_state")).get("inventory"),
        _safe_dict(state.get("party_state")).get("inventory"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return {
                "currency": _safe_dict(candidate.get("currency")),
                "items": _safe_list(candidate.get("items")),
            }
        if isinstance(candidate, list) and candidate:
            return {"items": candidate}
    return {"currency": {}, "items": []}


def _initial_state_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in transcript:
        before = _safe_dict(row.get("before_state"))
        if before:
            return before
        turn_result = _safe_dict(row.get("turn_result"))
        state = _safe_dict(turn_result.get("initial_simulation_state"))
        if state:
            return state
    return {}


def build_pm_report_summary(model: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _safe_dict(model.get("metrics"))
    progress = _safe_dict(metrics.get("progress_quality"))
    dialogue = _safe_dict(model.get("dialogue_coverage"))
    runtime_diag = _safe_dict(model.get("runtime_narration_diagnostics"))
    chapter = _safe_dict(model.get("chapter_status"))
    shortcomings = _safe_list(model.get("shortcomings"))

    return {
        "overall_status": "partial" if shortcomings else "good",
        "story_status": "good" if int(chapter.get("active_objective_count") or 0) > 0 else "warn",
        "dialogue_status": "good" if float(dialogue.get("social_turn_missing_npc_response_rate") or 0.0) == 0.0 else "warn",
        "provider_status": "good" if int(runtime_diag.get("provider_valid_turns") or 0) > 0 else "warn",
        "performance_status": "good",
        "headline": "The campaign can progress through a complete tavern investigation branch and continue into the bandit-road chapter.",
        "top_risks": shortcomings[:5],
        "key_numbers": {
            "turns": _safe_dict(model.get("summary")).get("turns_executed"),
            "meaningful_turns": progress.get("meaningful_turns"),
            "npc_response_rate": dialogue.get("npc_response_rate"),
            "provider_valid_turns": runtime_diag.get("provider_valid_turns"),
            "provider_repaired_turns": runtime_diag.get("provider_repaired_turns"),
            "active_objectives": chapter.get("active_objective_count"),
        },
    }


def render_campaign_report_html(model: Dict[str, Any]) -> str:
    summary = _safe_dict(model.get("summary"))
    metrics = _safe_dict(model.get("metrics"))
    health = _safe_dict(model.get("health"))
    progress_quality = _safe_dict(metrics.get("progress_quality"))
    performance = _safe_dict(metrics.get("performance"))
    story_variety = _safe_dict(metrics.get("story_variety"))
    latest_state = _safe_dict(model.get("latest_state"))
    chapter_status = _safe_dict(model.get("chapter_status"))
    pm_summary = _safe_dict(model.get("pm_summary"))
    pm_status = _status_class(pm_summary.get("overall_status"))

    timeline_html = []
    for row in _safe_list(model.get("timeline")):
        npc = _safe_dict(row.get("npc"))
        fired_hooks = _safe_list(row.get("fired_hooks"))
        hook_badges = " ".join(_render_badge(_safe_dict(h).get("hook_id"), "hook") for h in fired_hooks)
        categories = " ".join(
            _render_badge(category, "category")
            for category in _safe_list(_safe_dict(row.get("progress_delta")).get("categories"))
        )
        quality = _safe_str(_safe_dict(row.get("progress_quality")).get("quality"))
        timeline_html.append(
            f"""
            <article class="turn-card">
               <div class="turn-header">
                 <h3>Turn {_esc(row.get("turn_index"))}</h3>
                 <div>
                   {_render_badge(quality or "unknown", "quality")}
                   {_render_badge(str(_safe_dict(row.get("performance")).get("turn_total_ms", "")) + " ms", "category")}
                 </div>
               </div>
              <div class="player-action"><strong>Player:</strong> {_esc(row.get("player_action"))}</div>
              <div class="narration"><strong>Narration:</strong> {_esc(row.get("narration") or "[no narration extracted]")}</div>
              <div class="npc-line"><strong>NPC:</strong> {_esc(npc.get("speaker") or "[none]")} — {_esc(npc.get("line") or "[no NPC line extracted]")}</div>
              <div class="badges">
                {_render_badge("dialogue:" + _safe_str(row.get("dialogue_source") or "none"), "category")}
                {categories} {hook_badges}
                {_render_badge("missing_npc_response", "quality") if row.get("missing_npc_response") else ""}
                {_render_badge("echoed_narration", "quality") if row.get("echoed_narration") else ""}
              </div>
              <details>
                <summary>Turn debug</summary>
                <pre>{_json(row)}</pre>
              </details>
            </article>
            """
        )

    npc_rows = [
        [
            row.get("name") or row.get("npc_id"),
            row.get("role") or row.get("occupation"),
            row.get("dialogue_turns", 0),
            row.get("history") or row.get("backstory") or "",
            row.get("biography") or row.get("bio") or "",
            row.get("growth") or row.get("arc") or "",
        ]
        for row in _safe_list(model.get("npcs"))
    ]

    css = """
   :root {
     --bg: #0b1020;
     --panel: #ffffff;
     --panel2: #f6f8fc;
     --ink: #172033;
     --text: #172033;
     --muted: #64748b;
     --accent: #315efb;
     --accent2: #7c3aed;
     --good: #12805c;
     --warn: #b7791f;
     --bad: #c2410c;
     --border: #d9e1f2;
     --shadow: 0 20px 60px rgba(15, 23, 42, 0.12);
   }
   body {
     margin: 0;
     font-family: Inter, Segoe UI, Arial, sans-serif;
     background: linear-gradient(135deg, #edf3ff 0%, #f8fafc 45%, #f5f3ff 100%);
     color: var(--text);
     line-height: 1.5;
   }
   header {
     padding: 34px 42px;
     border-bottom: 1px solid var(--border);
     background: rgba(255,255,255,0.88);
     position: sticky;
     top: 0;
     z-index: 3;
     backdrop-filter: blur(16px);
     box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08);
   }
   h1, h2, h3 { margin: 0 0 12px; }
   h1 { font-size: 30px; letter-spacing: -0.03em; }
   h2 { font-size: 22px; letter-spacing: -0.02em; }
   h3 { font-size: 16px; color: var(--ink); }
   main { padding: 30px; max-width: 1500px; margin: 0 auto; }
   section {
     background: rgba(255,255,255,0.94);
     border: 1px solid var(--border);
     border-radius: 24px;
     padding: 24px;
     margin-bottom: 24px;
     box-shadow: var(--shadow);
   }
   .grid {
     display: grid;
     grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
     gap: 16px;
   }
   .metric {
     background: var(--panel2);
     border: 1px solid var(--border);
     border-radius: 18px;
     padding: 16px;
   }
    .metric .value { font-size: 28px; font-weight: 850; color: var(--accent); letter-spacing: -0.03em; }
    .bar-row {
      display: grid;
      grid-template-columns: 220px minmax(160px, 1fr) 90px;
      gap: 12px;
      align-items: center;
      margin: 10px 0;
    }
    .bar-label { font-weight: 700; color: #334155; }
    .bar-track {
      height: 12px;
      background: #e2e8f0;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid #dbe3ef;
    }
    .bar-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      border-radius: 999px;
    }
    .bar-value { color: var(--muted); font-variant-numeric: tabular-nums; text-align: right; }
    .section-lede {
      color: var(--muted);
      font-size: 15px;
      max-width: 980px;
      margin-top: -4px;
    }
    .card-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .story-card {
      background: var(--panel2);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
    }
    .story-card h3 { margin-bottom: 6px; }
    .kv-table th { width: 220px; }
    .muted { color: var(--muted); }
   .good { color: var(--good); }
   .warn { color: var(--warn); }
   .bad { color: var(--bad); }
   .hero {
     background: linear-gradient(135deg, #1d4ed8, #7c3aed);
     color: white;
     border: 0;
   }
   .hero .muted { color: rgba(255,255,255,0.78); }
   .hero .metric { background: rgba(255,255,255,0.14); border-color: rgba(255,255,255,0.22); color: white; }
   .hero .metric .value { color: white; }
   .status-pill {
     display: inline-block;
     padding: 6px 11px;
     border-radius: 999px;
     font-weight: 700;
     font-size: 12px;
     background: #e0e7ff;
     color: #3730a3;
     margin-left: 6px;
   }
   .status-pill.good { background: #dcfce7; color: #166534; }
   .status-pill.warn { background: #fef3c7; color: #92400e; }
   .status-pill.bad { background: #fee2e2; color: #991b1b; }
   table {
     width: 100%;
     border-collapse: collapse;
     overflow: hidden;
     border-radius: 14px;
   }
   th, td {
     border-bottom: 1px solid var(--border);
     padding: 10px 12px;
     text-align: left;
     vertical-align: top;
   }
    th { color: #334155; background: #eef2ff; }
    tr:nth-child(even) td { background: #f8fafc; }
    .npc-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    .npc-card, .journal-entry { border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin: 8px 0; background: #fafafa; }
    .npc-card h3 { margin-top: 0; }
    .report-quick-links {
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      padding: 12px;
      margin: 16px 0;
      background: #f8fafc;
    }
    .report-quick-links nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .report-quick-links a {
      display: inline-block;
      padding: 6px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      background: white;
      text-decoration: none;
    }
    #campaign-journal, #quest-progress, #npc-evolution {
      scroll-margin-top: 20px;
    }
    .header-journal-link {
      font-weight: 700;
    }
    .turn-card {
     background: var(--panel2);
     border: 1px solid var(--border);
     border-radius: 18px;
     padding: 16px;
     margin-bottom: 14px;
   }
   .turn-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
   .player-action, .narration, .npc-line { margin: 10px 0; }
   .badge {
     display: inline-block;
     padding: 4px 9px;
     border-radius: 999px;
     background: #e2e8f0;
     color: #334155;
     font-size: 12px;
     margin: 2px;
     border: 1px solid var(--border);
   }
   .badge.hook { background: #dcfce7; color: #166534; }
   .badge.category { background: #dbeafe; color: #1d4ed8; }
   .badge.quality { background: #fef3c7; color: #92400e; }
   pre {
     white-space: pre-wrap;
     overflow-x: auto;
     background: #0f172a;
     border: 1px solid var(--border);
     border-radius: 14px;
     padding: 12px;
     color: #d7ddff;
   }
   details { margin-top: 10px; }
   summary { cursor: pointer; color: var(--accent); font-weight: 700; }
   nav a { color: var(--accent); margin-right: 16px; text-decoration: none; }
   .tech-details {
     background: #f8fafc;
     border: 1px solid var(--border);
     border-radius: 16px;
     padding: 12px 14px;
     margin-top: 12px;
   }
   .two-col {
     display: grid;
     grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
     gap: 18px;
   }
   @media (max-width: 900px) {
     .two-col { grid-template-columns: 1fr; }
     header { position: static; }
   }
   """
    arc_cards_html = "".join(
        '<div class="story-card">'
        f'<h3>{_esc(arc.get("title"))}</h3>'
        f'<p><strong>Stage:</strong> {_esc(arc.get("stage"))} · <strong>Status:</strong> {_esc(arc.get("status"))}</p>'
        f'<p><strong>Completed Objectives:</strong> {_esc(arc.get("completed_count"))} · <strong>Active Objectives:</strong> {_esc(arc.get("active_count"))}</p>'
        f'{_render_bar("Arc Pressure", arc.get("pressure", 0), max_value=100)}'
        '</div>'
        for arc in _safe_list(_safe_dict(model.get("story_arc_view")).get("arcs"))
    )
    milestone_pm_rows = [
        [
            row.get("arc_id"),
            row.get("title"),
            row.get("status"),
            row.get("priority"),
            row.get("completed_turn_index"),
        ]
        for row in _safe_list(model.get("milestones"))
    ]
    player_view = _safe_dict(model.get("player_progression_view"))
    inventory_start_view = _safe_dict(model.get("inventory_start_view"))
    inventory_end_view = _safe_dict(model.get("inventory_end_view"))
    location_cards_html = "".join(
        '<div class="story-card">'
        f'<h3>{_esc(loc.get("name"))}</h3>'
        f'<p><strong>Turns:</strong> {_esc(loc.get("turn_range"))} · <strong>Turn Count:</strong> {_esc(loc.get("turn_count"))}</p>'
        f'<p>{_esc(loc.get("summary"))}</p>'
        f'<p><strong>NPCs:</strong> {_esc(", ".join(_safe_list(loc.get("npcs"))) or "None captured")}</p>'
        f'<p><strong>Objectives:</strong> {_esc(", ".join(_safe_list(loc.get("objectives"))) or "None captured")}</p>'
        f'{_render_json_details("Location events", loc.get("events"))}'
        '</div>'
        for loc in _safe_list(_safe_dict(model.get("location_journey")).get("locations"))
    )
    progress_quality_bars = "\n".join(
        [
            _render_progress_bar("Meaningful Progress Rate", progress_quality.get("meaningful_progress_rate")),
            _render_progress_bar("Churn-only Rate", progress_quality.get("churn_only_rate")),
            _render_progress_bar("Weak Progress Rate", progress_quality.get("weak_progress_rate")),
            _render_progress_bar("No-change Rate", progress_quality.get("no_change_rate")),
        ]
    )
    stage_values = [
        _safe_dict(v).get("total_ms", 0) / 1000.0
        for v in _safe_dict(performance.get("stage_summary")).values()
    ]
    max_stage_seconds = max(stage_values or [1.0])
    performance_stage_bars = "\n".join(
        _render_bar(
            key.replace("_ms", "").replace("_", " ").title(),
            _safe_dict(value).get("total_ms", 0) / 1000.0,
            max_value=max_stage_seconds,
            suffix="s",
        )
        for key, value in _safe_dict(performance.get("stage_summary")).items()
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Autoplay Campaign Report</title>
  <style>{css}</style>
</head>
<body>
 <header>
   <h1>Autoplay Campaign Report <span class="status-pill {pm_status}">{_esc(pm_summary.get("overall_status") or "unknown")}</span></h1>
   <div class="muted">Session {_esc(summary.get("session_id"))} · Strategy {_esc(summary.get("strategy_profile") or summary.get("strategy"))} · Turns {_esc(summary.get("turns_executed"))}</div>
     <nav>
      <a href="#summary">Summary</a>
      <a class="header-journal-link" href="#campaign-journal">Journal</a>
      <a href="#quest-progress">Quests</a>
      <a href="#npc-evolution">Evolution</a>
      <a href="#story-so-far">Story</a>
      <a href="#arcs">Arcs</a>
      <a href="#locations">Locations</a>
      <a href="#variety">Variety</a>
      <a href="#npcs">NPC Cast</a>
     <a href="#inventory">Inventory</a>
     <a href="#dialogue-coverage">Dialogue</a>
      <a href="#performance">Performance</a>
      <a href="#console-log">Console</a>
      <a href="#timeline">Timeline</a>
     <a href="#shortcomings">Shortcomings</a>
     <a href="#debug">Debug</a>
    </nav>
 </header>
 <main>
   <section id="summary" class="hero">
     <h2>Executive Summary</h2>
     <p style="font-size:18px; max-width: 980px;">{_esc(pm_summary.get("headline"))}</p>
     <div class="grid">
       <div class="metric"><div class="value">{_esc(summary.get("turns_executed"))}</div><div>Turns Executed</div></div>
       <div class="metric"><div class="value">{_esc(metrics.get("story_hook_fire_count"))}</div><div>Story Hooks Fired</div></div>
       <div class="metric"><div class="value">{_esc(progress_quality.get("meaningful_turns"))}</div><div>Meaningful Turns</div></div>
       <div class="metric"><div class="value">{_esc(progress_quality.get("meaningful_progress_rate"))}</div><div>Meaningful Progress Rate</div></div>
       <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("npc_response_rate"))}</div><div>NPC Response Rate</div></div>
       <div class="metric"><div class="value">{_esc(_safe_dict(model.get("chapter_status")).get("active_objective_count"))}</div><div>Active Objectives</div></div>
     </div>
      {_render_json_details("Technical summary JSON", {"summary": summary, "health": health, "pm_summary": pm_summary})}
      </section>

  {_render_report_quick_links(model)}
  {_render_calendar_and_journal(model.get("campaign_calendar_summary") or {}, model.get("player_journal_summary") or {})}
  {_render_quest_progress(model.get("quest_progress_summary") or {})}
  {_render_npc_evolution_cards(model.get("npc_evolution_report_summary") or {})}

   <section id="story-so-far">
    <h2>Story So Far</h2>
    <p class="section-lede">A readable summary of what happened in the campaign before the technical diagnostics.</p>
    {_render_paragraphs(model.get("story_so_far_paragraph"))}
    {_render_json_details("Story timeline summary inputs", {"milestones": model.get("milestones"), "journal_entries": model.get("journal_entries"), "hook_counts": model.get("hook_counts")})}
  </section>

  <section id="setting">
    <h2>Lore, Setting, and Director Setup</h2>
    <p class="section-lede">The premise, stakes, and setting context that frame the campaign run.</p>
    {_render_paragraphs(model.get("lore_setting_paragraph"))}
    <div class="card-list">
      {''.join(
        f'<div class="story-card"><h3>{_esc(row.get("title") or row.get("name") or row.get("id"))}</h3><p>{_esc(row.get("text") or row.get("description") or row.get("summary"))}</p></div>'
        for row in _safe_list(model.get("lore"))
      )}
    </div>
    {_render_json_details("Director state JSON", _safe_dict(latest_state.get("campaign_director_state")))}
  </section>

  <section id="arcs">
    <h2>Story Arc Status</h2>
    <p class="section-lede">A product/story view of campaign branches, active objectives, and completed beats.</p>
    <div class="card-list">
      {arc_cards_html}
    </div>
    <h3>Objectives / Milestones</h3>
    {_render_table(["Arc", "Objective", "Status", "Priority", "Completed Turn"], milestone_pm_rows)}
    {_render_json_details("Story arcs JSON", model.get("story_arcs"))}
    {_render_json_details("Milestones JSON", model.get("milestones"))}
   </section>

  <section id="locations">
    <h2>Location Journey</h2>
    <p class="section-lede">Where the run traveled, what happened there, who was involved, and what objectives were tied to each place.</p>
    <div class="card-list">
      {location_cards_html}
    </div>
    {_render_json_details("Location journey JSON", model.get("location_journey"))}
  </section>

  <section id="variety">
    <h2>Story Variety</h2>
    <p class="section-lede">Identifies which campaign seed ran and gives stable signatures for comparing story setups across multiple autoplay runs.</p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(story_variety.get("resolved_seed"))}</div><div>Resolved Seed</div></div>
      <div class="metric"><div class="value">{_esc(story_variety.get("randomized"))}</div><div>Randomized</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(story_variety.get("story_signature")).get("signature_hash"))}</div><div>Story Signature</div></div>
      <div class="metric"><div class="value">{_esc(story_variety.get("branch_signature_hash"))}</div><div>Branch Signature</div></div>
    </div>
    {_render_json_details("Story variety JSON", story_variety)}
  </section>

    <section id="run-validity">
    <h2>Run Validity</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(metrics.get("player_agent_exception_count"))}</div><div>Player-Agent Exceptions</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("fallback_player_actions"))}</div><div>Fallback Player Actions</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("fallback_player_action_rate"))}</div><div>Fallback Action Rate</div></div>
    </div>
    <p class="muted">A high fallback rate means this campaign reflects deterministic fallback action selection more than true LLM-player behavior.</p>
  </section>

  <section id="chapter-status">
    <h2>Chapter Status</h2>
    <p class="section-lede">Current campaign chapter, active story goals, completed goals, and recommended next direction.</p>
    {_render_chapter_status_cards(chapter_status)}
  </section>

  <section id="product-evaluation">
    <h2>Product Evaluation</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(pm_summary.get("story_status"))}</div><div>Story Continuity</div></div>
      <div class="metric"><div class="value">{_esc(pm_summary.get("dialogue_status"))}</div><div>Dialogue Coverage</div></div>
      <div class="metric"><div class="value">{_esc(pm_summary.get("provider_status"))}</div><div>Provider Narration</div></div>
      <div class="metric"><div class="value">{_esc(pm_summary.get("performance_status"))}</div><div>Performance</div></div>
    </div>
    <h3>Top Risks / Follow-ups</h3>
    {("<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in _safe_list(pm_summary.get("top_risks"))) + "</ul>") if _safe_list(pm_summary.get("top_risks")) else '<p class="good">No major PM-level risks detected.</p>'}
  </section>

  <section id="player">
    <h2>Player Character Progression / Stats</h2>
    <p class="section-lede">A readable snapshot of level, XP, core stats, and progression events.</p>
    {_render_paragraphs(model.get("character_progression_paragraph"))}
    <div class="two-col">
      <div>
        <h3>Character Summary</h3>
        {_render_key_value_table(_safe_list(player_view.get("summary_rows")))}
      </div>
      <div>
        <h3>Starting Stats</h3>
        {_render_table(["Stat", "Value"], _safe_list(player_view.get("stats_rows")))}
      </div>
    </div>
    <h3>Recent Progression Events</h3>
    {_render_table(["Turn", "Type", "Amount", "Reason", "Level"], _safe_list(player_view.get("recent_progression_rows")))}
    {_render_json_details("Player progression JSON", model.get("player_progression"))}
  </section>

  <section id="inventory">
    <h2>Inventory: Start vs End</h2>
    <p class="muted">Shows whether the campaign changed carried items, currency, or inventory-like state during the run.</p>
    <div class="two-col">
      <div>
        <h3>Starting Inventory</h3>
        <h4>Currency</h4>
        {_render_table(["Currency", "Amount"], _safe_list(inventory_start_view.get("currency_rows")))}
        <h4>Items</h4>
        {_render_table(["Item", "Qty", "Type", "Description"], _safe_list(inventory_start_view.get("item_rows")))}
      </div>
      <div>
        <h3>Ending Inventory</h3>
        <h4>Currency</h4>
        {_render_table(["Currency", "Amount"], _safe_list(inventory_end_view.get("currency_rows")))}
        <h4>Items</h4>
        {_render_table(["Item", "Qty", "Type", "Description"], _safe_list(inventory_end_view.get("item_rows")))}
      </div>
    </div>
    {_render_json_details("Raw inventory start/end JSON", {"start": model.get("inventory_start"), "end": model.get("inventory_end")})}
   </section>

  <section id="npcs">
    <h2>NPC Cast, Biography, and Growth</h2>
    <p class="muted">A product/story view of who appeared, why they matter, and how their relationship or role changed.</p>
    {_render_table(["Name", "Role", "Dialogue Turns", "History", "Biography", "Growth / Arc"], npc_rows)}
    {_render_json_details("NPC dialogue counts", model.get("npc_dialogue_counts"))}
    {_render_json_details("NPC progression state", _safe_dict(_safe_dict(latest_state.get("npc_progression_state")).get("npcs")))}
  </section>

  <section id="dialogue-coverage">
    <h2>Dialogue Coverage</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("npc_response_turn_count"))}</div><div>Turns with NPC Response</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("social_turn_missing_npc_response_count"))}</div><div>Social Turns Missing NPC Response</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("hook_dialogue_turn_count"))}</div><div>Hook Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("base_runtime_dialogue_turn_count"))}</div><div>Base Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("real_runtime_dialogue_turn_count"))}</div><div>Real Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("real_runtime_provider_dialogue_turn_count"))}</div><div>Provider Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("echoed_narration_turn_count"))}</div><div>Echoed Narration Turns</div></div>
    </div>
    <details>
      <summary>Dialogue coverage debug</summary>
      <pre>{_json(model.get("dialogue_coverage"))}</pre>
      </details>
    </section>

  <section id="performance">
    <h2>Performance Metrics</h2>
    <p class="section-lede">Runtime speed and where time is spent. Playability latency separates the blocking turn path from background narration/checkpoint/report work.</p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_number(performance.get("campaign_wall_seconds"), 2))}s</div><div>Campaign Wall Time</div></div>
      <div class="metric"><div class="value">{_esc(performance.get("turns_per_second"))}</div><div>Turns / Second</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("avg_turn_ms")))}</div><div>Average Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("p95_turn_ms")))}</div><div>p95 Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("max_turn_ms")))}</div><div>Max Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("artifact_write_ms")))}</div><div>Report Write Time</div></div>
    </div>
    <h3>Playability Latency</h3>
    <p class="muted">
      Autoplay blocking includes the LLM player-agent. Human-equivalent blocking excludes the player-agent because a real player supplies the action.
    </p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("avg_human_playable_blocking_ms")))}</div><div>Avg Human-Equivalent Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("p95_human_playable_blocking_ms")))}</div><div>p95 Human-Equivalent Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("max_human_playable_blocking_ms")))}</div><div>Max Human-Equivalent Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("avg_playable_blocking_ms")))}</div><div>Avg Autoplay Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("p95_playable_blocking_ms")))}</div><div>p95 Autoplay Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_seconds_from_ms(performance.get("max_playable_blocking_ms")))}</div><div>Max Autoplay Blocking Turn</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("background_jobs")).get("total_jobs"))}</div><div>Background Jobs</div></div>
      <div class="metric"><div class="value">{_esc(_number(_safe_dict(model.get("background_jobs")).get("background_job_seconds"), 2))}s</div><div>Background Worker Time</div></div>
    </div>
    <h3>Evaluation Wall Time</h3>
    {performance_stage_bars}
    {_render_json_details("Stage summary JSON", performance.get("stage_summary") or {})}
    {_render_json_details("Provider trace summary JSON", model.get("provider_trace_summary") or {})}
    {_render_json_details("Manual harness trace summary JSON", model.get("manual_harness_trace_summary") or {})}
    {_render_json_details("Session turn trace summary JSON", model.get("turn_perf_trace_summary") or {})}
    {_render_json_details("Player-agent trace summary JSON", model.get("player_agent_trace_summary") or {})}
    {_render_json_details("Deferred narration trace summary JSON", model.get("deferred_narration_trace_summary") or {})}
    {_render_json_details("Deferred advisory trace summary JSON", model.get("deferred_advisory_trace_summary") or {})}
    {_render_json_details("Performance budget summary JSON", model.get("performance_budget_summary") or {})}
    {_render_json_details("Background prompt budget summary JSON", model.get("background_prompt_budget_summary") or {})}
    {_render_json_details("Combined quality shape summary JSON", model.get("combined_quality_shape_summary") or {})}
    {_render_json_details("Player-agent prompt budget summary JSON", model.get("player_agent_prompt_budget_summary") or {})}
    {_render_json_details("Player-agent cache summary JSON", model.get("player_agent_cache_summary") or {})}
    {_render_json_details("Deferred advisory promotion summary JSON", model.get("deferred_advisory_promotion_summary") or {})}
    {_render_json_details("NPC evolution summary JSON", model.get("npc_evolution_summary") or {})}
    {_render_json_details("NPC evolution profile persistence summary JSON", model.get("npc_evolution_profile_persistence_summary") or {})}
    {_render_json_details("NPC profile load summary JSON", model.get("npc_profile_load_summary") or {})}
    {_render_json_details("Profile-grounded output summary JSON", model.get("profile_grounded_output_summary") or {})}
    {_render_json_details("NPC arc progression summary JSON", model.get("npc_arc_progression_summary") or {})}
    {_render_json_details("Promotion target grounding summary JSON", model.get("promotion_target_grounding_summary") or {})}
    {_render_json_details("Quality gate summary JSON", model.get("quality_gate_summary") or {})}
    {_render_json_details("Slowest turns JSON", performance.get("slowest_turns") or [])}
     {_render_json_details("Background job summary JSON", model.get("background_jobs") or {})}
  </section>

  <section id="quality">
    <h2>Progress Quality & Action Diversity</h2>
    <p class="section-lede">How often the campaign produced meaningful story/game progress versus weak progress, churn, or no visible change.</p>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(progress_quality.get("churn_only_turns"))}</div><div>Churn-only Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("weak_progress_turns"))}</div><div>Weak Progress Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("no_change_turns"))}</div><div>No-change Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("action_diversity")).get("action_diversity_rate"))}</div><div>Action Diversity Rate</div></div>
    </div>
    <h3>Progress Distribution</h3>
    {progress_quality_bars}
    {_render_json_details("Progress category counts", model.get("category_counts"))}
    <h3>Hook Counts</h3>
    {_render_json_details("Hook counts", model.get("hook_counts"))}
  </section>

  <section id="runtime-narration-diagnostics">
    <h2>Runtime Narration Diagnostics</h2>
    <p class="muted">Provider validity, repair, fallback, and method-call diagnostics.</p>
    {_render_json_details("Runtime narration diagnostics JSON", model.get("runtime_narration_diagnostics"))}
   </section>

    <section id="timeline">
    <h2>Turn-by-Turn Story Timeline with AI/NPC Responses</h2>
    {''.join(timeline_html)}
   </section>

    {_render_console_log_summary(model.get("console_log_summary") or {})}
    {_render_json_details("Console log summary JSON", model.get("console_log_summary") or {})}

    <section id="debug">
      <h2>Raw Debug Appendix</h2>
      <p><strong>Latest state source:</strong> {_esc(model.get("latest_state_source"))}</p>
      {_render_json_details("Story beat fallback summary JSON", model.get("story_beat_summary") or {})}
      {_render_json_details("Manual turn error summary JSON", model.get("manual_turn_error_summary") or {})}
      {_render_json_details("Latest Simulation State", latest_state)}
      {_render_json_details("Summary JSON", summary)}
      {_render_json_details("Metrics JSON", metrics)}
    </section>
</main>
</body>
</html>"""


def write_campaign_report(
    *,
    output_dir: Path,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    health: Dict[str, Any],
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model = build_campaign_report_model(
        transcript=transcript,
        summary=summary,
        metrics=metrics,
        health=health,
    )
    model_path = output_dir / "autoplay-campaign-report.json"
    html_path = output_dir / "autoplay-campaign-report.html"
    model_path.write_text(
        json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    html_path.write_text(render_campaign_report_html(model), encoding="utf-8")
    return {
        "campaign_report_json": str(model_path),
        "campaign_report_html": str(html_path),
    }