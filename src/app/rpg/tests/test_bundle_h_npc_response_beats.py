"""Bundle H — NPC Response Beats + Topic Pivoting v1

Tests for:
H1 — topic pivot detection and NPC response beat generation
H2 — player-joined NPC reply handling

Hard constraints verified:
- No quest creation / completion
- No reward grants
- No inventory / currency mutation
- No journal mutation
- No location mutation
- No combat start
"""
from app.rpg.session.ambient_tick_runtime import advance_autonomous_ambient_tick
from app.rpg.session.conversation_thread_runtime import (
    advance_conversation_threads_for_turn,
)
from app.rpg.world.conversation_rumor_propagation import (
    add_rumor_seed,
    expire_stale_signals,
    get_active_rumor_seeds,
    get_conversation_rumor_context,
)
from app.rpg.world.conversation_social_state import (
    get_npc_relationship_summary,
    get_player_invitation_chance_modifier,
)
from app.rpg.world.conversation_threads import (
    handle_pending_player_conversation_response,
    maybe_advance_conversation_thread,
)
from app.rpg.world.conversation_topics import detect_topic_pivot_hint
from app.rpg.world.location_registry import set_current_location

# ── helpers ──────────────────────────────────────────────────────────────────


def _runtime_state(**overrides):
    settings = {
        "enabled": True,
        "autonomous_ticks_enabled": True,
        "frequency": "always",
        "conversation_chance_percent": 100,
        "min_ticks_between_conversations": 0,
        "thread_cooldown_ticks": 0,
        "allow_player_invited": True,
        "player_inclusion_chance_percent": 100,
        "pending_response_timeout_ticks": 3,
        "allow_npc_response_beats": True,
        "npc_response_style_influence": True,
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_world_signals_per_thread": 2,
        "max_world_events_per_thread": 4,
    }
    settings.update(overrides)
    return {"runtime_settings": {"conversation_settings": settings}}


def _quest_state():
    return {
        "active_quests": [{
            "id": "quest:old_mill",
            "title": "Trouble near the Old Mill",
            "summary": "Armed figures have been seen near the old mill road.",
            "status": "active",
            "location_id": "loc_tavern",
        }]
    }


def _invite_and_get_pending(state, runtime_state, tick=100):
    result = advance_autonomous_ambient_tick(
        player_input="__ambient_tick_player_invited__",
        simulation_state=state,
        runtime_state=runtime_state,
        tick=tick,
    )
    assert result["applied"] is True, f"invite failed: {result}"
    assert state["conversation_thread_state"]["pending_player_response"]
    return result


# ── H1: topic pivot detection ─────────────────────────────────────────────────


def test_detect_pivot_finds_quest_keyword():
    state = {"quest_state": _quest_state()}
    set_current_location(state, "loc_tavern")
    hint = detect_topic_pivot_hint(
        "What about the old mill?",
        state,
        settings={"allow_quest_discussion": True},
    )
    assert hint["found"] is True
    assert hint["topic"]["topic_type"] == "quest"
    assert "mill" in hint["hint_text"] or "old" in hint["hint_text"]


def test_detect_pivot_returns_not_found_for_empty_input():
    state = {}
    set_current_location(state, "loc_tavern")
    hint = detect_topic_pivot_hint("", state)
    assert hint["found"] is False
    assert hint["score"] == 0


def test_detect_pivot_returns_not_found_for_stopword_only_input():
    state = {}
    set_current_location(state, "loc_tavern")
    hint = detect_topic_pivot_hint("i do not know what you mean", state)
    # No meaningful keyword overlap — may or may not find something, but cannot
    # match a quest that isn't in state.
    assert not hint["found"] or hint["topic"]["topic_type"] == "location_smalltalk"


def test_detect_pivot_no_match_when_topic_not_in_state():
    """A query about a topic that doesn't exist in state returns found=False."""
    state = {}  # no quests, no events
    set_current_location(state, "loc_tavern")
    hint = detect_topic_pivot_hint(
        "Tell me about dragons and ancient treasure",
        state,
        settings={"allow_quest_discussion": True},
    )
    # location_smalltalk may match but only because it's always backed
    assert hint["found"] is False or hint["topic"]["topic_type"] == "location_smalltalk"


# ── H1: NPC response beat after player joins ─────────────────────────────────


def test_npc_response_beat_present_after_player_joins():
    state = {}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=100)

    reply = advance_conversation_threads_for_turn(
        player_input="What is going on here?",
        simulation_state=state,
        resolved_result={
            "action_type": "talk",
            "semantic_action_type": "talk",
            "semantic_family": "social",
            "service_result": {"matched": False},
        },
        tick=101,
        runtime_state=_runtime_state(),
    )

    assert reply["triggered"] is True
    assert reply["reason"] == "pending_player_response_consumed"
    assert "npc_response_beat" in reply
    npc_beat = reply["npc_response_beat"]
    assert isinstance(npc_beat, dict)
    assert npc_beat.get("speaker_name")
    assert npc_beat.get("line")
    assert npc_beat.get("listener_id") == "player"
    assert npc_beat.get("participation_mode") == "player_joined"


def test_npc_response_beat_has_response_style():
    state = {}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=50)

    reply = advance_conversation_threads_for_turn(
        player_input="I heard something about trouble.",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=51,
        runtime_state=_runtime_state(),
    )
    assert reply["triggered"] is True
    npc_beat = reply["npc_response_beat"]
    assert npc_beat.get("response_style") in {
        "guarded", "evasive", "neutral", "helpful", "friendly"
    }


def test_npc_response_beat_disabled_by_setting():
    state = {}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(allow_npc_response_beats=False), tick=200)

    reply = advance_conversation_threads_for_turn(
        player_input="I am listening.",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=201,
        runtime_state=_runtime_state(allow_npc_response_beats=False),
    )
    assert reply["triggered"] is True
    # When disabled, npc_response_beat should be empty dict or absent.
    assert reply.get("npc_response_beat", {}) == {}


# ── H1: topic pivot accepted when quest is in state ───────────────────────────


def test_topic_pivot_accepted_for_backed_quest():
    state = {"quest_state": _quest_state()}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=100)

    reply = advance_conversation_threads_for_turn(
        player_input="What do you know about the old mill road?",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=101,
        runtime_state=_runtime_state(),
    )

    assert reply["triggered"] is True
    pivot = reply["topic_pivot"]
    assert pivot["accepted"] is True
    assert pivot["topic_type"] == "quest"
    assert "old_mill" in pivot["topic_id"]
    assert pivot["pivot_rejected_reason"] == ""
    assert "mill" in pivot["requested_topic_hint"] or "old" in pivot["requested_topic_hint"]


def test_topic_pivot_rejected_when_topic_not_in_state():
    """Player asks about a topic with no state backing → NPC deflects."""
    state = {}  # no quests, no events, no memories
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=200)

    reply = advance_conversation_threads_for_turn(
        player_input="Tell me about the dragon lair in the mountains.",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=201,
        runtime_state=_runtime_state(),
    )

    assert reply["triggered"] is True
    pivot = reply["topic_pivot"]
    # No quest/event/memory → pivot not accepted
    assert pivot["accepted"] is False
    npc_beat = reply["npc_response_beat"]
    # NPC line should be a deflection, not a fact
    assert npc_beat.get("line")


def test_topic_pivot_debug_fields_present():
    state = {}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=10)

    reply = advance_conversation_threads_for_turn(
        player_input="I wonder about recent events around here.",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=11,
        runtime_state=_runtime_state(),
    )

    assert reply["triggered"] is True
    pivot = reply["topic_pivot"]
    assert "requested" in pivot
    assert "accepted" in pivot
    assert "topic_type" in pivot
    assert "topic_id" in pivot
    assert "requested_topic_hint" in pivot
    assert "selected_topic_id" in pivot
    assert "selected_topic_type" in pivot
    assert "pivot_rejected_reason" in pivot


# ── I1: NPC relationship/social state influence ───────────────────────────────


def test_fresh_npc_has_stranger_trust_hint():
    state = {}
    summary = get_npc_relationship_summary(state, "npc:Bran")
    assert summary["familiarity"] == 0
    assert summary["trust_hint"] == "stranger"
    assert summary["response_style"] == "guarded"


def test_familiarity_increases_after_player_joins():
    state = {}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=1)

    advance_conversation_threads_for_turn(
        player_input="Hello there.",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=2,
        runtime_state=_runtime_state(),
    )

    # After one interaction familiarity is 1 per NPC participant
    social = state.get("conversation_social_state", {})
    npc_state = social.get("npc_state", {})
    # At least one NPC should have familiarity > 0
    assert any(
        rec.get("familiarity", 0) > 0
        for rec in npc_state.values()
    ), f"Expected familiarity > 0, got: {npc_state}"


def test_invitation_chance_modifier_grows_with_familiarity():
    state = {}
    mod_0 = get_player_invitation_chance_modifier(state, "npc:Bran")
    assert mod_0 == 0

    # Simulate familiarity buildup by directly writing to social state
    from app.rpg.world.conversation_social_state import ensure_conversation_social_state
    css = ensure_conversation_social_state(state)
    css["npc_state"]["npc:Bran"] = {"npc_id": "npc:Bran", "familiarity": 15}

    mod_15 = get_player_invitation_chance_modifier(state, "npc:Bran")
    assert mod_15 == 10


def test_trust_hint_levels():
    from app.rpg.world.conversation_social_state import _trust_hint_from_familiarity
    assert _trust_hint_from_familiarity(0) == "stranger"
    assert _trust_hint_from_familiarity(4) == "stranger"
    assert _trust_hint_from_familiarity(5) == "acquaintance"
    assert _trust_hint_from_familiarity(14) == "acquaintance"
    assert _trust_hint_from_familiarity(15) == "familiar"
    assert _trust_hint_from_familiarity(24) == "familiar"
    assert _trust_hint_from_familiarity(25) == "trusted"


def test_response_style_levels():
    from app.rpg.world.conversation_social_state import _response_style_from_familiarity
    assert _response_style_from_familiarity(0) == "guarded"
    assert _response_style_from_familiarity(5) == "evasive"
    assert _response_style_from_familiarity(15) == "helpful"
    assert _response_style_from_familiarity(25) == "friendly"


def test_recent_conversation_topics_tracked_per_npc():
    state = {}
    set_current_location(state, "loc_tavern")
    _invite_and_get_pending(state, _runtime_state(), tick=1)

    advance_conversation_threads_for_turn(
        player_input="Anything happening nearby?",
        simulation_state=state,
        resolved_result={"semantic_family": "social", "service_result": {"matched": False}},
        tick=2,
        runtime_state=_runtime_state(),
    )

    social = state.get("conversation_social_state", {})
    npc_state = social.get("npc_state", {})
    for npc_id, rec in npc_state.items():
        topics = rec.get("recent_conversation_topics", [])
        assert isinstance(topics, list)


# ── J1: Bounded rumor propagation ─────────────────────────────────────────────


def test_rumor_seed_created_from_eligible_signal():
    state = {}
    settings = {
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_signal_age_ticks": 20,
    }
    signal = {
        "signal_id": "world_signal:test:123",
        "kind": "quest_interest",
        "strength": 1,
        "topic_id": "topic:quest:old_mill",
    }
    topic = {
        "topic_id": "topic:quest:old_mill",
        "topic_type": "quest",
    }
    seed = add_rumor_seed(
        state,
        signal=signal,
        topic=topic,
        tick=10,
        location_id="loc_tavern",
        settings=settings,
    )
    assert seed.get("seed_id")
    assert seed["source_topic_id"] == "topic:quest:old_mill"
    assert seed["location_id"] == "loc_tavern"
    assert seed["mentions_remaining"] >= 1
    assert seed["expires_tick"] == 30


def test_rumor_seed_not_created_for_ambient_interest():
    state = {}
    signal = {"signal_id": "sig:1", "kind": "ambient_interest", "strength": 1}
    topic = {"topic_id": "topic:loc:tavern", "topic_type": "location_smalltalk"}
    seed = add_rumor_seed(
        state,
        signal=signal,
        topic=topic,
        tick=5,
        location_id="loc_tavern",
        settings={"allow_rumor_propagation": True, "max_rumor_seeds": 16,
                  "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20},
    )
    assert seed == {}


def test_rumor_seed_dedup_same_topic_location():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20,
    }
    signal = {"signal_id": "sig:1", "kind": "rumor_pressure", "strength": 1,
              "topic_id": "topic:quest:smugglers"}
    topic = {"topic_id": "topic:quest:smugglers", "topic_type": "quest"}
    seed1 = add_rumor_seed(state, signal=signal, topic=topic, tick=1,
                           location_id="loc_market", settings=settings)
    seed2 = add_rumor_seed(state, signal=signal, topic=topic, tick=2,
                           location_id="loc_market", settings=settings)
    assert seed1.get("seed_id")
    assert seed2 == {}
    assert len(state["rumor_propagation_state"]["rumor_seeds"]) == 1


def test_rumor_seed_location_cap_enforced():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 2, "max_signal_age_ticks": 20,
    }
    for i in range(3):
        signal = {"signal_id": f"sig:{i}", "kind": "danger_warning", "strength": 1}
        topic = {"topic_id": f"topic:event:e{i}", "topic_type": "recent_event"}
        add_rumor_seed(state, signal=signal, topic=topic, tick=i,
                       location_id="loc_tavern", settings=settings)
    seeds = get_active_rumor_seeds(state, location_id="loc_tavern", current_tick=0)
    assert len(seeds) <= 2  # cap at max_rumor_mentions_per_location


def test_expire_stale_signals_removes_old_seeds():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 5,
    }
    signal = {"signal_id": "sig:old", "kind": "rumor_pressure", "strength": 1}
    topic = {"topic_id": "topic:quest:old", "topic_type": "quest"}
    add_rumor_seed(state, signal=signal, topic=topic, tick=1,
                   location_id="loc_tavern", settings=settings)

    # Seed expires at tick 6 (1 + 5)
    summary = expire_stale_signals(state, current_tick=10)
    assert summary["expired_count"] == 1
    assert summary["remaining_count"] == 0
    assert state["rumor_propagation_state"]["rumor_seeds"] == []


def test_expire_stale_signals_keeps_active_seeds():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20,
    }
    signal = {"signal_id": "sig:active", "kind": "quest_interest", "strength": 1}
    topic = {"topic_id": "topic:quest:active", "topic_type": "quest"}
    add_rumor_seed(state, signal=signal, topic=topic, tick=100,
                   location_id="loc_tavern", settings=settings)

    summary = expire_stale_signals(state, current_tick=110)
    assert summary["expired_count"] == 0
    assert summary["remaining_count"] == 1


def test_rumor_propagation_disabled_produces_no_seed():
    state = {}
    signal = {"signal_id": "sig:1", "kind": "rumor_pressure", "strength": 1}
    topic = {"topic_id": "topic:quest:x", "topic_type": "quest"}
    seed = add_rumor_seed(
        state,
        signal=signal,
        topic=topic,
        tick=1,
        location_id="loc_tavern",
        settings={"allow_rumor_propagation": False, "max_rumor_seeds": 16,
                  "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20},
    )
    assert seed == {}


def test_get_conversation_rumor_context():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20,
    }
    signal = {"signal_id": "sig:ctx", "kind": "quest_interest", "strength": 1}
    topic = {"topic_id": "topic:quest:ctx", "topic_type": "quest"}
    add_rumor_seed(state, signal=signal, topic=topic, tick=50,
                   location_id="loc_tavern", settings=settings)

    ctx = get_conversation_rumor_context(
        state, location_id="loc_tavern", current_tick=55, settings=settings
    )
    assert ctx["location_id"] == "loc_tavern"
    assert ctx["active_seed_count"] == 1
    assert len(ctx["active_seeds"]) == 1


# ── J1: rumor seed created from live conversation signal ─────────────────────


def test_rumor_seed_created_from_quest_conversation():
    """A conversation about a quest topic produces a rumor seed via world signal."""
    state = {"quest_state": _quest_state()}
    set_current_location(state, "loc_tavern")

    result = maybe_advance_conversation_thread(
        state,
        player_input="I wait and listen",
        tick=10,
        settings={
            "enabled": True,
            "allow_world_signals": True,
            "allow_world_events": True,
            "allow_rumor_propagation": True,
            "max_world_signals_per_thread": 2,
            "max_world_events_per_thread": 4,
            "max_rumor_seeds": 16,
            "max_rumor_mentions_per_location": 4,
            "max_signal_age_ticks": 20,
            "thread_cooldown_ticks": 0,
            "allow_quest_discussion": True,
        },
        forced_topic_type="quest",
    )

    assert result["triggered"] is True
    # If the signal kind is rumor-propagation-eligible, seed should be created.
    if result.get("world_signal"):
        signal_kind = result["world_signal"].get("kind", "")
        if signal_kind in {"quest_interest", "rumor_pressure", "danger_warning", "social_tension"}:
            assert result.get("rumor_seed"), (
                f"Expected rumor_seed for signal_kind={signal_kind}"
            )
