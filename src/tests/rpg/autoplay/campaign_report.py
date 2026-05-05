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
    if _safe_dict(ai_payload.get("npc")).get("line"):
        return "raw_ai_payload"

    hook_display = extract_story_hook_display(row)
    if _safe_dict(hook_display.get("npc")).get("line"):
        return "story_hook_display"

    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    if _safe_dict(manual_summary.get("raw_npc")).get("line"):
        return "raw_npc"

    if extract_conversation_beat(row).get("line"):
        return "conversation_beat"

    return "none"


def extract_dialogue(row: Dict[str, Any]) -> Dict[str, str]:
    turn_result = _safe_dict(row.get("turn_result"))
    manual_summary = _safe_dict(turn_result.get("manual_turn_summary"))
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    ai_payload = extract_turn_ai_payload(row)
    hook_display = extract_story_hook_display(row)
    npc_payload = _safe_dict(ai_payload.get("npc"))
    hook_npc = _safe_dict(hook_display.get("npc"))
    raw_npc = _safe_dict(manual_summary.get("raw_npc"))
    conversation_beat = extract_conversation_beat(row)

    speaker = _first_nonempty(
        npc_payload.get("speaker"),
        hook_npc.get("speaker"),
        raw_npc.get("speaker"),
        conversation_beat.get("speaker"),
        raw_result.get("npc_speaker"),
        _nested_get(raw_result, "npc", "speaker"),
        _nested_get(raw_result, "result", "npc", "speaker"),
        _nested_get(raw_result, "turn_contract", "npc", "speaker"),
        _nested_get(turn_result, "turn_contract", "npc", "speaker"),
    )
    line = _first_nonempty(
        npc_payload.get("line"),
        hook_npc.get("line"),
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
    raw_result = _safe_dict(manual_summary.get("raw_result"))
    return _first_nonempty(
        ai_payload.get("narration"),
        hook_display.get("narration"),
        turn_result.get("narration"),
        manual_summary.get("raw_narration"),
        raw_result.get("narration"),
        _nested_get(raw_result, "result", "narration"),
    )


def _latest_state_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in reversed(transcript):
        turn_result = _safe_dict(row.get("turn_result"))
        state = _safe_dict(turn_result.get("simulation_state"))
        if state:
            return state
    return {}


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
    journal_entries = _safe_list(model.get("journal_entries"))

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
        if row.get("dialogue_source") in {"raw_ai_payload", "raw_npc", "conversation_beat"}
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


def build_campaign_report_model(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    health: Dict[str, Any],
) -> Dict[str, Any]:
    latest_state = _latest_state_from_transcript(transcript)
    quality = _safe_dict(metrics.get("progress_quality"))
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
            }
        )

    dialogue_coverage = compute_dialogue_coverage(timeline)

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
        "shortcomings": shortcomings,
    }
    model["story_so_far_paragraph"] = build_story_so_far_paragraph(model)
    model["lore_setting_paragraph"] = build_lore_setting_paragraph(latest_state)
    model["character_progression_paragraph"] = build_character_progression_paragraph(latest_state)
    model["chapter_status"] = build_chapter_status(latest_state, model)
    return model


def _render_badge(text: str, cls: str = "") -> str:
    return f'<span class="badge {html.escape(cls)}">{_esc(text)}</span>'


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


def render_campaign_report_html(model: Dict[str, Any]) -> str:
    summary = _safe_dict(model.get("summary"))
    metrics = _safe_dict(model.get("metrics"))
    health = _safe_dict(model.get("health"))
    progress_quality = _safe_dict(metrics.get("progress_quality"))
    latest_state = _safe_dict(model.get("latest_state"))

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
                <div>{_render_badge(quality or "unknown", "quality")}</div>
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

    arc_rows = [
        [
            row.get("arc_id"),
            row.get("title") or row.get("name"),
            row.get("stage"),
            row.get("status"),
            row.get("updated_turn_index"),
        ]
        for row in _safe_list(model.get("story_arcs"))
    ]
    milestone_rows = [
        [
            row.get("arc_id"),
            row.get("milestone_id"),
            row.get("title"),
            row.get("status"),
            row.get("priority"),
            row.get("completed_turn_index"),
        ]
        for row in _safe_list(model.get("milestones"))
    ]
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
    journal_rows = [
        [
            row.get("turn_index"),
            row.get("entry_id"),
            row.get("title"),
            row.get("text"),
            ", ".join(str(x) for x in _safe_list(row.get("tags"))),
        ]
        for row in _safe_list(model.get("journal_entries"))
    ]
    lore_rows = [
        [
            row.get("type"),
            row.get("id"),
            row.get("title") or row.get("name"),
            row.get("text") or row.get("description") or row.get("summary"),
        ]
        for row in _safe_list(model.get("lore"))
    ]
    event_rows = [
        [
            row.get("turn_index"),
            row.get("event_id"),
            row.get("title"),
            row.get("summary"),
            row.get("severity"),
        ]
        for row in _safe_list(model.get("story_events"))
    ]

    shortcomings = _safe_list(model.get("shortcomings"))
    shortcomings_html = (
        "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in shortcomings) + "</ul>"
        if shortcomings
        else '<p class="good">No major shortcomings detected by report heuristics.</p>'
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Autoplay Campaign Report</title>
  <style>
    :root {{
      --bg: #0f1220;
      --panel: #171b2e;
      --panel2: #202640;
      --text: #f3f5ff;
      --muted: #aab1d6;
      --accent: #8fb7ff;
      --good: #7ee787;
      --warn: #f2cc60;
      --bad: #ff7b72;
      --border: #303859;
    }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background: radial-gradient(circle at top left, #1c2548, var(--bg));
      color: var(--text);
      line-height: 1.5;
    }}
    header {{
      padding: 32px;
      border-bottom: 1px solid var(--border);
      background: rgba(15,18,32,0.88);
      position: sticky;
      top: 0;
      z-index: 3;
      backdrop-filter: blur(10px);
    }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    main {{ padding: 28px; max-width: 1500px; margin: 0 auto; }}
    section {{
      background: rgba(23,27,46,0.96);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      margin-bottom: 22px;
      box-shadow: 0 12px 35px rgba(0,0,0,0.22);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }}
    .metric {{
      background: var(--panel2);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
    }}
    .metric .value {{ font-size: 28px; font-weight: 800; color: var(--accent); }}
    .muted {{ color: var(--muted); }}
    .good {{ color: var(--good); }}
    .warn {{ color: var(--warn); }}
    .bad {{ color: var(--bad); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 12px;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--accent); background: #202640; }}
    tr:nth-child(even) td {{ background: rgba(255,255,255,0.025); }}
    .turn-card {{
      background: var(--panel2);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 14px;
    }}
    .turn-header {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    .player-action, .narration, .npc-line {{ margin: 10px 0; }}
    .badge {{
      display: inline-block;
      padding: 4px 9px;
      border-radius: 999px;
      background: #2b3356;
      color: var(--text);
      font-size: 12px;
      margin: 2px;
      border: 1px solid var(--border);
    }}
    .badge.hook {{ background: #173d2a; color: #a7f3c1; }}
    .badge.category {{ background: #27375f; color: #bcd3ff; }}
    .badge.quality {{ background: #3d2f17; color: #ffd98a; }}
    pre {{
      white-space: pre-wrap;
      overflow-x: auto;
      background: #0b0e19;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      color: #d7ddff;
    }}
    details {{ margin-top: 10px; }}
    summary {{ cursor: pointer; color: var(--accent); }}
    nav a {{ color: var(--accent); margin-right: 16px; text-decoration: none; }}
  </style>
</head>
<body>
<header>
  <h1>Autoplay Campaign Report</h1>
  <div class="muted">Session {_esc(summary.get("session_id"))} · Strategy {_esc(summary.get("strategy_profile") or summary.get("strategy"))} · OK {_esc(summary.get("ok"))}</div>
   <nav>
     <a href="#summary">Summary</a>
     <a href="#dialogue-coverage">Dialogue</a>
     <a href="#timeline">Timeline</a>
    <a href="#arcs">Story Arcs</a>
    <a href="#npcs">NPCs</a>
    <a href="#lore">Lore</a>
    <a href="#shortcomings">Shortcomings</a>
    <a href="#debug">Debug</a>
  </nav>
</header>
<main>
  <section id="summary">
    <h2>Executive Summary</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(summary.get("turns_executed"))}</div><div>Turns Executed</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("story_hook_fire_count"))}</div><div>Story Hooks Fired</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("meaningful_turns"))}</div><div>Meaningful Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("meaningful_progress_rate"))}</div><div>Meaningful Progress Rate</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("checkpoint_failure_count"))}</div><div>Checkpoint Failures</div></div>
      <div class="metric"><div class="value">{_esc(metrics.get("state_bound_warning_count"))}</div><div>State Bound Warnings</div></div>
    </div>
    <h3>Health Warnings</h3>
    <pre>{_json(health.get("warnings") or [])}</pre>
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

  <section id="dialogue-coverage">
    <h2>Dialogue Coverage</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("npc_response_turn_count"))}</div><div>Turns with NPC Response</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("social_turn_missing_npc_response_count"))}</div><div>Social Turns Missing NPC Response</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("hook_dialogue_turn_count"))}</div><div>Hook Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("base_runtime_dialogue_turn_count"))}</div><div>Base Runtime Dialogue Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("dialogue_coverage")).get("echoed_narration_turn_count"))}</div><div>Echoed Narration Turns</div></div>
    </div>
    <details>
      <summary>Dialogue coverage debug</summary>
      <pre>{_json(model.get("dialogue_coverage"))}</pre>
    </details>
  </section>

  <section id="story-so-far">
    <h2>Story So Far</h2>
    {_render_paragraphs(model.get("story_so_far_paragraph"))}
  </section>

  <section id="chapter-status">
    <h2>Chapter Status</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("chapter_status")).get("completed_objective_count"))}</div><div>Completed Objectives</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("chapter_status")).get("active_objective_count"))}</div><div>Active Objectives</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("chapter_status")).get("current_stage"))}</div><div>Current Arc Stage</div></div>
    </div>
    <p>{_esc(_safe_dict(model.get("chapter_status")).get("recommendation"))}</p>
    <pre>{_json(model.get("chapter_status"))}</pre>
  </section>

  <section id="setting">
    <h2>Lore, Setting, and Director Setup</h2>
    {_render_paragraphs(model.get("lore_setting_paragraph"))}
    <h3>Director State</h3>
    <pre>{_json(_safe_dict(latest_state.get("campaign_director_state")))}</pre>
  </section>

  <section id="character-progression">
    <h2>Character Progression Summary</h2>
    {_render_paragraphs(model.get("character_progression_paragraph"))}
  </section>

  <section id="shortcomings">
    <h2>Detected Shortcomings / Evaluation Notes</h2>
    {shortcomings_html}
  </section>

  <section id="arcs">
    <h2>Story Arc Progression</h2>
    {_render_table(["Arc ID", "Title", "Stage", "Status", "Updated Turn"], arc_rows)}
    <h3>Objectives / Milestones</h3>
    {_render_table(["Arc ID", "Milestone ID", "Title", "Status", "Priority", "Completed Turn"], milestone_rows)}
  </section>

  <section id="journal">
    <h2>Campaign Journal / Story Summary</h2>
    {_render_table(["Turn", "Entry ID", "Title", "Text", "Tags"], journal_rows)}
  </section>

  <section id="events">
    <h2>Story Events / Branch Outcomes</h2>
    {_render_table(["Turn", "Event ID", "Title", "Summary", "Severity"], event_rows)}
  </section>

  <section id="npcs">
    <h2>NPCs Introduced / Biography / Growth</h2>
    {_render_table(["Name", "Role", "Dialogue Turns", "History", "Biography", "Growth / Arc"], npc_rows)}
    <h3>NPC Dialogue Counts</h3>
    <pre>{_json(model.get("npc_dialogue_counts"))}</pre>
    <h3>NPC Progression State</h3>
    <pre>{_json(_safe_dict(_safe_dict(latest_state.get("npc_progression_state")).get("npcs")))}</pre>
  </section>

   <section id="player">
     <h2>Player Character Progression / Stats</h2>
     <p>{_esc(model.get("character_progression_paragraph"))}</p>
     <pre>{_json(model.get("player_progression"))}</pre>
   </section>

  <section id="lore">
    <h2>Lore & Worldbuilding</h2>
    {_render_table(["Type", "ID", "Title/Name", "Text"], lore_rows)}
  </section>

  <section id="quality">
    <h2>Progress Quality & Action Diversity</h2>
    <div class="grid">
      <div class="metric"><div class="value">{_esc(progress_quality.get("churn_only_turns"))}</div><div>Churn-only Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("weak_progress_turns"))}</div><div>Weak Progress Turns</div></div>
      <div class="metric"><div class="value">{_esc(progress_quality.get("no_change_turns"))}</div><div>No-change Turns</div></div>
      <div class="metric"><div class="value">{_esc(_safe_dict(model.get("action_diversity")).get("action_diversity_rate"))}</div><div>Action Diversity Rate</div></div>
    </div>
    <h3>Progress Categories</h3>
    <pre>{_json(model.get("category_counts"))}</pre>
    <h3>Hook Counts</h3>
    <pre>{_json(model.get("hook_counts"))}</pre>
  </section>

  <section id="timeline">
    <h2>Turn-by-Turn Story Timeline with AI/NPC Responses</h2>
    {''.join(timeline_html)}
  </section>

  <section id="debug">
    <h2>Raw Debug Appendix</h2>
    <details>
      <summary>Latest Simulation State</summary>
      <pre>{_json(latest_state)}</pre>
    </details>
    <details>
      <summary>Summary JSON</summary>
      <pre>{_json(summary)}</pre>
    </details>
    <details>
      <summary>Metrics JSON</summary>
      <pre>{_json(metrics)}</pre>
    </details>
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