from __future__ import annotations

from typing import Any, Dict, List

from .conversation_participants import (
    find_candidate_conversation_groups,
    select_initiator,
    select_next_speaker,
)
from .conversation_settings import resolve_conversation_settings
from .conversation_templates import build_template_line
from .conversation_topics import build_conversation_topic_candidates
from .npc_conversations import (
    append_conversation_line,
    build_conversation_line,
    build_conversation_state,
    close_conversation,
    ensure_conversation_state,
    get_conversation_lines,
    list_active_conversations,
    trim_conversation_state,
    upsert_conversation,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _player_location(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    runtime_state = _safe_dict(runtime_state)
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    return _safe_str(runtime_state.get("current_location_id") or player_state.get("location_id"))


def _conversation_exists_for_group(simulation_state: Dict[str, Any], location_id: str, participants: List[str], topic_anchor: str) -> bool:
    target = sorted([_safe_str(x) for x in participants if _safe_str(x)])
    for conv in list_active_conversations(simulation_state, location_id=location_id):
        if sorted(conv.get("participants") or []) == target:
            topic = _safe_dict(conv.get("topic"))
            if _safe_str(topic.get("anchor")) == _safe_str(topic_anchor):
                return True
    return False


def open_conversation(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    *,
    kind: str,
    location_id: str,
    participants: List[str],
    topic: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    settings = resolve_conversation_settings(simulation_state, runtime_state)
    initiator_id = select_initiator(simulation_state, participants)
    player_loc = _player_location(simulation_state, runtime_state)
    conversation = build_conversation_state(
        kind=kind,
        location_id=location_id,
        participants=participants,
        initiator_id=initiator_id,
        topic=topic,
        max_turns=min(
            settings["max_conversation_turns"],
            max(2, settings["avg_conversation_turns"]),
        ),
        player_can_intervene=settings["player_intervention_enabled"],
        player_present=(player_loc == location_id),
        tick=tick,
    )
    upsert_conversation(simulation_state, conversation)
    return conversation


def _resolve_speaker_name(simulation_state: Dict[str, Any], speaker_id: str) -> str:
    npc_index = _safe_dict(_safe_dict(simulation_state).get("npc_index"))
    row = _safe_dict(npc_index.get(speaker_id))
    return _safe_str(row.get("name")) or _safe_str(speaker_id)


def build_next_conversation_line(conversation: Dict[str, Any], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    settings = resolve_conversation_settings(simulation_state, runtime_state)
    speaker_id = select_next_speaker(conversation, simulation_state)
    recent_lines = get_conversation_lines(simulation_state, conversation.get("conversation_id"))
    speaker_display = _resolve_speaker_name(simulation_state, speaker_id)

    if settings.get("llm_expand_npc_conversations"):
        try:
            from app.rpg.ai.conversation_gateway import (
                generate_recorded_conversation_line,
            )
            from app.rpg.llm_app_gateway import build_app_llm_gateway
            llm_gateway = build_app_llm_gateway()
            mode = _safe_str(_safe_dict(runtime_state).get("mode")).strip().lower() or "live"
            conv_id = _safe_str(conversation.get("conversation_id"))
            turn_num = int(conversation.get("turn_count", 0) or 0) + 1
            record_key = f"conversation_line:{conv_id}:{turn_num}"

            if mode == "live":
                record = generate_recorded_conversation_line(
                    llm_gateway,
                    conversation,
                    speaker_id,
                    simulation_state,
                    runtime_state,
                    recent_lines,
                )
                if record and _safe_dict(record).get("parsed"):
                    # Record into replay structures
                    llm_records = runtime_state.setdefault("llm_records", []) if isinstance(runtime_state, dict) else []
                    llm_records_index = runtime_state.setdefault("llm_records_index", {}) if isinstance(runtime_state, dict) else {}
                    record_index = len(llm_records)
                    llm_records.append(dict(record))
                    llm_records_index[record_key] = record_index

                    parsed = _safe_dict(record.get("parsed"))
                    return build_conversation_line(
                        conversation_id=conv_id,
                        turn=turn_num,
                        speaker=parsed.get("speaker", speaker_id),
                        speaker_name=speaker_display,
                        text=parsed.get("text", ""),
                        kind=parsed.get("kind", "statement"),
                        created_tick=tick,
                        source="llm",
                    )
            else:
                # Replay mode: read back from recorded data
                llm_records = runtime_state.get("llm_records", []) if isinstance(runtime_state, dict) else []
                llm_records_index = _safe_dict(runtime_state.get("llm_records_index")) if isinstance(runtime_state, dict) else {}
                record_index = llm_records_index.get(record_key)
                if isinstance(record_index, int) and record_index < len(llm_records):
                    replay_record = _safe_dict(llm_records[record_index])
                    parsed = _safe_dict(replay_record.get("parsed"))
                    if parsed.get("text"):
                        return build_conversation_line(
                            conversation_id=conv_id,
                            turn=turn_num,
                            speaker=parsed.get("speaker", speaker_id),
                            speaker_name=speaker_display,
                            text=parsed.get("text", ""),
                            kind=parsed.get("kind", "statement"),
                            created_tick=tick,
                            source="llm",
                        )
                raise RuntimeError(f"Missing recorded conversation line for replay: {record_key}")
        except ImportError:
            pass

    line_payload = build_template_line(conversation, speaker_id, simulation_state, runtime_state)
    return build_conversation_line(
        conversation_id=conversation.get("conversation_id"),
        turn=int(conversation.get("turn_count", 0) or 0) + 1,
        speaker=speaker_id,
        speaker_name=line_payload.get("speaker_name", speaker_display),
        text=line_payload.get("text", ""),
        kind=line_payload.get("kind", "statement"),
        created_tick=tick,
        source="template",
    )


def should_close_conversation(conversation: Dict[str, Any], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> bool:
    conversation = _safe_dict(conversation)
    if _safe_str(conversation.get("status")) != "active":
        return True
    if int(conversation.get("turn_count", 0) or 0) >= int(conversation.get("max_turns", 1) or 1):
        return True
    return False


def try_start_ambient_conversations(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    settings = resolve_conversation_settings(simulation_state, runtime_state)
    if not settings["ambient_conversations_enabled"]:
        return simulation_state

    ensure_conversation_state(simulation_state)
    player_loc = _player_location(simulation_state, runtime_state)
    candidate_groups = find_candidate_conversation_groups(simulation_state, player_loc, tick)
    started = 0

    for group in candidate_groups:
        topics = build_conversation_topic_candidates(simulation_state, runtime_state, player_loc, group, tick)
        if not topics:
            continue
        topic = topics[0]
        if _conversation_exists_for_group(simulation_state, player_loc, group, topic.get("anchor", "")):
            continue
        open_conversation(
            simulation_state,
            runtime_state,
            kind="ambient_npc_conversation",
            location_id=player_loc,
            participants=group,
            topic=topic,
            tick=tick,
        )
        started += 1
        if len(list_active_conversations(simulation_state, location_id=player_loc)) >= 2:
            break
        if started >= 2:
            break
    return simulation_state


def try_start_party_reaction_conversation(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], player_action: Dict[str, Any], tick: int) -> Dict[str, Any]:
    settings = resolve_conversation_settings(simulation_state, runtime_state)
    if not settings["party_reaction_interrupts_enabled"]:
        return simulation_state

    runtime_state["last_player_action"] = dict(player_action or {})
    player_loc = _player_location(simulation_state, runtime_state)
    groups = find_candidate_conversation_groups(simulation_state, player_loc, tick)
    if not groups:
        return simulation_state

    group = groups[0]
    topics = build_conversation_topic_candidates(simulation_state, runtime_state, player_loc, group, tick)
    topics = [t for t in topics if _safe_str(_safe_dict(t).get("type")) in {"plan_reaction", "risk_conflict"}]
    if not topics:
        return simulation_state

    topic = topics[0]
    if not _conversation_exists_for_group(simulation_state, player_loc, group, topic.get("anchor", "")):
        open_conversation(
            simulation_state,
            runtime_state,
            kind="party_reaction",
            location_id=player_loc,
            participants=group,
            topic=topic,
            tick=tick,
        )
    return simulation_state


def advance_active_conversations(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    from .conversation_beats import (
        append_beat,
        build_beat_from_conversation_line,
        ensure_beats_state,
    )
    from .conversation_world_signals import (
        enqueue_signals,
        ensure_signal_state,
        extract_signals_from_beat,
    )

    ensure_beats_state(simulation_state)
    ensure_signal_state(runtime_state)

    for conv in list_active_conversations(simulation_state):
        conv = dict(conv)
        if should_close_conversation(conv, simulation_state, runtime_state, tick):
            close_conversation(simulation_state, conv.get("conversation_id"), reason="completed")
            continue

        line = build_next_conversation_line(conv, simulation_state, runtime_state, tick)
        append_conversation_line(simulation_state, conv.get("conversation_id"), line)

        # 4C-B: Build authoritative beat from line
        beat = build_beat_from_conversation_line(conv, line, tick)
        append_beat(simulation_state, beat)

        # 4C-E: Extract world signals from beat
        conv_settings = resolve_conversation_settings(simulation_state, runtime_state)
        if conv_settings.get("allow_conversation_world_signals", True):
            signals = extract_signals_from_beat(beat, conv)
            if signals:
                enqueue_signals(runtime_state, signals)
                conv["world_effects_emitted"] = int(conv.get("world_effects_emitted", 0) or 0) + len(signals)

        conv["turn_count"] = int(conv.get("turn_count", 0) or 0) + 1
        conv["beat_count"] = int(conv.get("beat_count", 0) or 0) + 1
        conv["updated_tick"] = int(tick or 0)
        conv["last_speaker_id"] = _safe_str(line.get("speaker"))
        conv["intervention_pending"] = bool(conv.get("player_can_intervene") and conv.get("player_present"))
        upsert_conversation(simulation_state, conv)

        if should_close_conversation(conv, simulation_state, runtime_state, tick):
            close_conversation(simulation_state, conv.get("conversation_id"), reason="completed")

    trim_conversation_state(simulation_state)
    return simulation_state


def run_conversation_tick(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    from .conversation_pivots import evaluate_pivots
    from .conversation_settings import should_suppress_conversations
    from .conversation_world_signals import apply_pending_signals

    ensure_conversation_state(simulation_state)

    # 4C-F: Check combat/stealth suppression
    settings = resolve_conversation_settings(simulation_state, runtime_state)
    if should_suppress_conversations(simulation_state, settings):
        trim_conversation_state(simulation_state)
        return simulation_state

    try_start_ambient_conversations(simulation_state, runtime_state, tick)
    advance_active_conversations(simulation_state, runtime_state, tick)

    # 4C-D: Evaluate pivots after advancing
    evaluate_pivots(simulation_state, runtime_state, tick)

    # 4C-E: Apply pending world signals
    simulation_state, runtime_state = apply_pending_signals(simulation_state, runtime_state)

    trim_conversation_state(simulation_state)
    return simulation_state
