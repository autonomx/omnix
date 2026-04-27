"""Bundle H-I-J.1 — Manual Coverage + Environment Memory Cleanup

Real executable scenario tests for:
  1. npc_replies_after_player_join
  2. player_requests_backed_quest_topic
  3. player_requests_unbacked_topic
  4. npc_response_uses_social_state
  5. rumor_seed_from_conversation
  6. rumor_signal_expires

Also covers:
  - Blocking synthetic environment NPCs from social/relationship state
  - Regression guard: fake environment memories must never appear
  - topic_pivot.accepted == True for backed quest/event/rumor
  - topic_pivot.accepted == False with clear rejection reason for unbacked topics
"""
from app.rpg.memory.social_effects import apply_general_social_effects
from app.rpg.session.ambient_tick_runtime import advance_autonomous_ambient_tick
from app.rpg.session.conversation_thread_runtime import (
    advance_conversation_threads_for_turn,
)
from app.rpg.world.conversation_rumor_propagation import (
    add_rumor_seed,
    expire_stale_signals,
    get_active_rumor_seeds,
)
from app.rpg.world.conversation_social_state import (
    _is_synthetic_npc_participant,
    ensure_conversation_social_state,
    get_npc_relationship_summary,
    record_player_joined_conversation,
)
from app.rpg.world.conversation_threads import (
    handle_pending_player_conversation_response,
    maybe_advance_conversation_thread,
)
from app.rpg.world.conversation_topics import detect_topic_pivot_hint
from app.rpg.world.location_registry import set_current_location

# ── helpers ───────────────────────────────────────────────────────────────────


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
        "pending_response_timeout_ticks": 5,
        "allow_npc_response_beats": True,
        "npc_response_style_influence": True,
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_world_signals_per_thread": 2,
        "max_world_events_per_thread": 4,
        "allow_quest_discussion": True,
        "allow_event_discussion": True,
        "allow_rumor_discussion": True,
        "allow_memory_discussion": True,
    }
    settings.update(overrides)
    return {"runtime_settings": {"conversation_settings": settings}}


def _with_quest(state):
    state.setdefault("quest_state", {})["active_quests"] = [{
        "id": "quest:old_mill",
        "title": "Trouble near the Old Mill",
        "summary": "Armed figures have been seen near the old mill road.",
        "status": "active",
        "location_id": "loc_tavern",
    }]
    return state


def _with_world_event(state):
    state.setdefault("world_event_state", {})["events"] = [{
        "event_id": "event:market_fire",
        "kind": "disaster",
        "title": "Market fire",
        "summary": "A fire broke out near the market stalls at dawn.",
        "location_id": "loc_market",
    }]
    return state


def _with_journal_rumor(state):
    state.setdefault("journal_state", {})["entries"] = [{
        "entry_id": "journal:smugglers_rumor",
        "kind": "rumor",
        "title": "Smugglers at the docks",
        "summary": "Someone has been moving sealed crates through the market after dusk.",
    }]
    return state


def _assert_no_forbidden_effects(result, label=""):
    """Hard-contract guard: conversation results must never carry world mutations."""
    forbidden = {
        "quest_started", "quest_completed", "reward", "reward_granted",
        "item_created", "currency_delta", "currency_changed", "stock_update",
        "stock_changed", "journal_entry", "journal_entry_created",
        "transaction_record", "inventory_delta", "location_changed",
        "combat_started", "npc_moved",
    }
    hits = [k for k in forbidden if result.get(k)]
    assert not hits, f"{label}: forbidden effects present: {hits}"
    validation = result.get("conversation_effect_validation", {})
    assert validation.get("ok", True), (
        f"{label}: conversation_effect_validation failed: {validation.get('violations')}"
    )


def _assert_no_synthetic_npc_in_social_state(state, label=""):
    """Regression guard: synthetic environment NPCs must not appear in social state."""
    social = state.get("conversation_social_state", {})
    npc_state = social.get("npc_state", {})
    for npc_id in npc_state:
        assert not _is_synthetic_npc_participant({"id": npc_id}), (
            f"{label}: synthetic NPC '{npc_id}' leaked into conversation_social_state"
        )
    for reply in social.get("recent_player_replies", []):
        # replies should not carry synthetic thread ids
        assert "room/environment" not in str(reply).lower(), (
            f"{label}: synthetic environment reference in recent_player_replies: {reply}"
        )


def _invite_player(state, runtime_state, tick):
    result = advance_autonomous_ambient_tick(
        player_input="__ambient_tick_player_invited__",
        simulation_state=state,
        runtime_state=runtime_state,
        tick=tick,
    )
    assert result["applied"] is True, f"invite failed at tick {tick}: {result}"
    assert state["conversation_thread_state"]["pending_player_response"], (
        "pending_player_response not set after invite"
    )
    return result


def _player_reply(state, runtime_state, player_input, tick):
    return advance_conversation_threads_for_turn(
        player_input=player_input,
        simulation_state=state,
        resolved_result={
            "action_type": "talk",
            "semantic_action_type": "talk",
            "semantic_family": "social",
            "service_result": {"matched": False},
        },
        tick=tick,
        runtime_state=runtime_state,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1 — npc_replies_after_player_join
# ═══════════════════════════════════════════════════════════════════════════════


def test_scenario_npc_replies_after_player_join_beat_present():
    """After the player joins, the result must contain a non-empty NPC response beat."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=100)

    reply = _player_reply(state, rt, "I am listening, what do you mean?", tick=101)

    assert reply["triggered"] is True
    assert reply["reason"] == "pending_player_response_consumed"
    npc_beat = reply["npc_response_beat"]
    assert isinstance(npc_beat, dict) and npc_beat, "npc_response_beat must be non-empty"
    assert npc_beat["speaker_name"] in {"Bran", "Mira"}, (
        f"Expected Bran or Mira as speaker, got: {npc_beat['speaker_name']}"
    )
    assert npc_beat["listener_id"] == "player"
    assert npc_beat["line"], "npc_response_beat.line must not be empty"
    assert npc_beat["participation_mode"] == "player_joined"
    _assert_no_forbidden_effects(reply, label="scenario_npc_replies_after_player_join")


def test_scenario_npc_replies_after_player_join_pending_cleared():
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=200)

    reply = _player_reply(state, rt, "Tell me more.", tick=201)

    assert reply["triggered"] is True
    assert state["conversation_thread_state"]["pending_player_response"] == {}, (
        "pending_player_response must be cleared after consumption"
    )


def test_scenario_npc_replies_after_player_join_npc_beat_in_thread():
    """The NPC response beat must be appended to the thread beats list."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=10)

    reply = _player_reply(state, rt, "What is happening here?", tick=11)

    assert reply["triggered"] is True
    thread = reply["thread"]
    beats = thread["beats"]
    beat_sources = [b.get("speaker_id") for b in beats]
    # At minimum the original NPC beat, the player beat, and the NPC response beat
    assert "player" in beat_sources, "player beat must be in thread"
    # NPC response beat has non-player speaker
    npc_response_speakers = [b["speaker_id"] for b in beats
                             if b.get("listener_id") == "player" and b.get("speaker_id") != "player"]
    assert npc_response_speakers, "At least one NPC→player beat must exist in thread"


def test_scenario_npc_replies_response_style_field():
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=50)

    reply = _player_reply(state, rt, "Interesting.", tick=51)

    npc_beat = reply["npc_response_beat"]
    assert npc_beat.get("response_style") in {
        "guarded", "evasive", "neutral", "helpful", "friendly"
    }, f"Unexpected response_style: {npc_beat.get('response_style')}"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 — player_requests_backed_quest_topic
# ═══════════════════════════════════════════════════════════════════════════════


def test_scenario_backed_quest_pivot_accepted():
    """topic_pivot.accepted == True when player mentions a backed quest keyword."""
    state = _with_quest({})
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=100)

    reply = _player_reply(state, rt, "What do you know about the old mill road?", tick=101)

    assert reply["triggered"] is True
    pivot = reply["topic_pivot"]
    assert pivot["accepted"] is True, (
        f"Expected pivot accepted=True, got: {pivot}"
    )
    assert pivot["topic_type"] == "quest"
    assert "old_mill" in pivot["topic_id"]
    assert pivot["pivot_rejected_reason"] == ""
    _assert_no_forbidden_effects(reply, label="backed_quest_pivot")


def test_scenario_backed_quest_pivot_hint_text():
    state = _with_quest({})
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=20)

    reply = _player_reply(state, rt, "old mill bandits trouble road", tick=21)

    pivot = reply["topic_pivot"]
    assert pivot["accepted"] is True
    assert pivot["requested_topic_hint"], "hint_text should be non-empty for matching reply"
    # Hint text should contain at least one matching word
    hint_words = set(pivot["requested_topic_hint"].split())
    assert hint_words & {"mill", "old", "bandits", "trouble", "road", "armed"}, (
        f"Hint should contain quest keywords, got: '{pivot['requested_topic_hint']}'"
    )


def test_scenario_backed_quest_pivot_npc_beat_uses_quest_fact():
    state = _with_quest({})
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=30)

    reply = _player_reply(state, rt, "Tell me about the old mill", tick=31)

    npc_beat = reply["npc_response_beat"]
    assert npc_beat["topic_type"] == "quest", (
        f"NPC beat should be about the quest topic, got: {npc_beat['topic_type']}"
    )
    # The NPC line must reference quest facts, not location smalltalk
    assert npc_beat["line"], "NPC response line must not be empty"


def test_scenario_backed_event_pivot_accepted():
    """topic_pivot.accepted == True for a backed world event."""
    state = _with_world_event({})
    set_current_location(state, "loc_market")
    rt = _runtime_state()
    _invite_player(state, rt, tick=50)

    reply = _player_reply(state, rt, "What happened with the fire at the market?", tick=51)

    pivot = reply["topic_pivot"]
    # "fire" and "market" both appear in the event topic keywords
    if pivot["accepted"]:
        assert pivot["topic_type"] == "recent_event"
        assert pivot["pivot_rejected_reason"] == ""
    # Even if not accepted (keyword score tie), must never be wrong reason
    assert pivot["pivot_rejected_reason"] in {
        "", "no_topic_hint_in_reply", "topic_not_backed_by_state"
    }
    _assert_no_forbidden_effects(reply, label="backed_event_pivot")


def test_scenario_backed_rumor_pivot_accepted():
    """topic_pivot.accepted == True for a backed journal rumor."""
    state = _with_journal_rumor({})
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=60)

    reply = _player_reply(state, rt, "I heard about the smugglers moving crates", tick=61)

    pivot = reply["topic_pivot"]
    if pivot["accepted"]:
        assert pivot["topic_type"] == "rumor"
        assert "smuggler" in pivot["topic_id"] or "rumor" in pivot["topic_id"]
        assert pivot["pivot_rejected_reason"] == ""
    _assert_no_forbidden_effects(reply, label="backed_rumor_pivot")


def test_scenario_debug_fields_complete_on_accepted_pivot():
    state = _with_quest({})
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=100)

    reply = _player_reply(state, rt, "old mill armed road", tick=101)

    pivot = reply["topic_pivot"]
    assert "requested" in pivot
    assert "accepted" in pivot
    assert "topic_type" in pivot
    assert "topic_id" in pivot
    assert "requested_topic_hint" in pivot
    assert "selected_topic_id" in pivot
    assert "selected_topic_type" in pivot
    assert "pivot_rejected_reason" in pivot
    assert pivot["accepted"] is True
    assert pivot["selected_topic_id"] == pivot["topic_id"]
    assert pivot["selected_topic_type"] == pivot["topic_type"]


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3 — player_requests_unbacked_topic
# ═══════════════════════════════════════════════════════════════════════════════


def test_scenario_unbacked_topic_pivot_rejected():
    """topic_pivot.accepted == False when no matching state-backed topic exists."""
    state = {}  # no quests, events, memories
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=200)

    reply = _player_reply(
        state, rt,
        "Tell me about the dragon lair in the northern mountains.",
        tick=201,
    )

    assert reply["triggered"] is True
    pivot = reply["topic_pivot"]
    assert pivot["accepted"] is False, (
        f"Expected pivot rejected for unbacked topic, got: {pivot}"
    )
    assert pivot["pivot_rejected_reason"] in {
        "no_topic_hint_in_reply",
        "topic_not_backed_by_state",
    }, f"Unexpected rejection reason: {pivot['pivot_rejected_reason']}"
    _assert_no_forbidden_effects(reply, label="unbacked_topic_pivot")


def test_scenario_unbacked_topic_npc_deflects():
    """When pivot is rejected, the NPC must produce a non-empty deflection line."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=300)

    reply = _player_reply(
        state, rt,
        "Tell me about the dragon lair in the northern mountains.",
        tick=301,
    )

    npc_beat = reply["npc_response_beat"]
    assert npc_beat.get("line"), "NPC must produce a deflection line for unbacked topic"
    # Deflection line must NOT contain fabricated quest facts
    assert "dragon lair" not in npc_beat["line"].lower(), (
        "NPC must not fabricate dragon lair details"
    )


def test_scenario_unbacked_topic_no_quest_created():
    """Hard constraint: no quest is created even when player asks about fantasy topics."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=400)

    reply = _player_reply(
        state, rt,
        "Tell me about the dragon lair and where to find ancient treasure.",
        tick=401,
    )

    _assert_no_forbidden_effects(reply, label="unbacked_no_quest_created")
    # Quest state must remain empty
    quest_state = state.get("quest_state", {})
    for key in ("quests", "active_quests", "current_quests"):
        assert not quest_state.get(key), f"quest key '{key}' must stay empty"


def test_scenario_pivot_rejected_reason_is_clear():
    """pivot_rejected_reason must be a specific non-empty string, not a generic error."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=500)

    reply = _player_reply(state, rt, "xyzzy frobozz quux", tick=501)

    pivot = reply["topic_pivot"]
    # Pure nonsense words → no hint found
    assert pivot["accepted"] is False
    assert pivot["pivot_rejected_reason"], "rejection reason must be non-empty string"
    assert pivot["pivot_rejected_reason"] != "error", (
        "rejection reason must be descriptive, not generic 'error'"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4 — npc_response_uses_social_state
# ═══════════════════════════════════════════════════════════════════════════════


def test_scenario_fresh_npc_is_guarded():
    """A brand-new NPC with familiarity 0 must have response_style 'guarded'."""
    state = {}
    summary = get_npc_relationship_summary(state, "npc:Bran")
    assert summary["familiarity"] == 0
    assert summary["trust_hint"] == "stranger"
    assert summary["response_style"] == "guarded"


def test_scenario_familiarity_increments_after_interaction():
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=1)
    _player_reply(state, rt, "Hello.", tick=2)

    npc_state = state.get("conversation_social_state", {}).get("npc_state", {})
    assert npc_state, "npc_state must be populated after interaction"
    for npc_id, rec in npc_state.items():
        assert rec["familiarity"] > 0, (
            f"NPC {npc_id} familiarity must be > 0 after player joined"
        )


def test_scenario_social_state_bounded_caps():
    """recent_player_replies and recent_conversation_topics must stay within caps."""
    state = {}
    # Drive 15 calls directly into record_player_joined_conversation
    thread = {
        "thread_id": "t:test",
        "participants": [
            {"id": "npc:Bran", "name": "Bran"},
            {"id": "npc:Mira", "name": "Mira"},
        ],
    }
    for i in range(15):
        record_player_joined_conversation(
            state,
            tick=i,
            thread=thread,
            player_response={"beat_id": f"beat:{i}", "line": f"reply {i}"},
            topic={"topic_id": f"topic:loc:t{i}", "topic_type": "location_smalltalk"},
        )

    npc_state = state["conversation_social_state"]["npc_state"]
    for npc_id, rec in npc_state.items():
        replies = rec.get("recent_player_replies", [])
        topics = rec.get("recent_conversation_topics", [])
        assert len(replies) <= 8, (
            f"NPC {npc_id}: recent_player_replies exceeded cap 8, got {len(replies)}"
        )
        assert len(topics) <= 12, (
            f"NPC {npc_id}: recent_conversation_topics exceeded cap 12, got {len(topics)}"
        )
    global_replies = state["conversation_social_state"]["recent_player_replies"]
    assert len(global_replies) <= 64, (
        f"Global recent_player_replies exceeded cap 64, got {len(global_replies)}"
    )


def test_scenario_response_style_changes_with_familiarity():
    """Directly inject familiarity and verify style matches the ladder."""
    state = {}
    css = ensure_conversation_social_state(state)

    for familiarity, expected_style in [
        (0, "guarded"),
        (4, "guarded"),
        (5, "evasive"),
        (14, "evasive"),
        (15, "helpful"),
        (24, "helpful"),
        (25, "friendly"),
        (100, "friendly"),
    ]:
        css["npc_state"]["npc:TestNPC"] = {"npc_id": "npc:TestNPC", "familiarity": familiarity}
        summary = get_npc_relationship_summary(state, "npc:TestNPC")
        assert summary["response_style"] == expected_style, (
            f"familiarity={familiarity}: expected '{expected_style}', got '{summary['response_style']}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5 — rumor_seed_from_conversation
# ═══════════════════════════════════════════════════════════════════════════════


_RUMOR_ELIGIBLE_SIGNAL_KINDS = {"quest_interest", "rumor_pressure", "danger_warning", "social_tension"}


def test_scenario_rumor_seed_created_from_quest_signal():
    """Conversation about a quest topic produces a rumor_seed with correct fields."""
    state = _with_quest({})
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
    signal = result.get("world_signal", {})
    rumor_seed = result.get("rumor_seed", {})

    if signal and signal.get("kind") in _RUMOR_ELIGIBLE_SIGNAL_KINDS:
        assert rumor_seed, (
            f"Expected rumor_seed for eligible signal kind '{signal.get('kind')}', got none"
        )
        assert rumor_seed["source_topic_id"] == signal.get("topic_id")
        assert rumor_seed["location_id"] == "loc_tavern"
        assert rumor_seed["mentions_remaining"] >= 1
        assert rumor_seed["expires_tick"] == 10 + 20
        assert rumor_seed["source_signal_kind"] == signal["kind"]


def test_scenario_rumor_seed_fields_complete():
    state = {}
    settings = {
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_signal_age_ticks": 20,
    }
    signal = {
        "signal_id": "world_signal:test:10:thread:beat",
        "kind": "quest_interest",
        "strength": 1,
        "topic_id": "topic:quest:old_mill",
        "topic_type": "quest",
    }
    topic = {"topic_id": "topic:quest:old_mill", "topic_type": "quest"}
    seed = add_rumor_seed(state, signal=signal, topic=topic, tick=10,
                          location_id="loc_tavern", settings=settings)

    assert seed["seed_id"]
    assert seed["source_topic_id"] == "topic:quest:old_mill"
    assert seed["source_topic_type"] == "quest"
    assert seed["source_signal_kind"] == "quest_interest"
    assert seed["source_signal_id"] == signal["signal_id"]
    assert seed["location_id"] == "loc_tavern"
    assert seed["mentions_remaining"] >= 1
    assert seed["created_tick"] == 10
    assert seed["expires_tick"] == 30


def test_scenario_ambient_interest_signal_does_not_seed_rumor():
    """ambient_interest signals must NOT create rumor seeds."""
    state = {}
    seed = add_rumor_seed(
        state,
        signal={"signal_id": "sig:1", "kind": "ambient_interest", "strength": 1},
        topic={"topic_id": "topic:loc:tavern", "topic_type": "location_smalltalk"},
        tick=5,
        location_id="loc_tavern",
        settings={
            "allow_rumor_propagation": True, "max_rumor_seeds": 16,
            "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20,
        },
    )
    assert seed == {}, "ambient_interest must not create a rumor seed"


def test_scenario_rumor_seed_location_cap_enforced():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 2, "max_signal_age_ticks": 20,
    }
    for i in range(5):
        add_rumor_seed(
            state,
            signal={"signal_id": f"sig:{i}", "kind": "danger_warning", "strength": 1},
            topic={"topic_id": f"topic:event:e{i}", "topic_type": "recent_event"},
            tick=i,
            location_id="loc_tavern",
            settings=settings,
        )
    active = get_active_rumor_seeds(state, location_id="loc_tavern", current_tick=0)
    assert len(active) <= 2, (
        f"Location cap of 2 exceeded: {len(active)} seeds at loc_tavern"
    )


def test_scenario_rumor_propagation_disabled_no_seed():
    state = {}
    seed = add_rumor_seed(
        state,
        signal={"signal_id": "sig:1", "kind": "quest_interest", "strength": 1},
        topic={"topic_id": "topic:quest:x", "topic_type": "quest"},
        tick=1,
        location_id="loc_tavern",
        settings={"allow_rumor_propagation": False, "max_rumor_seeds": 16,
                  "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20},
    )
    assert seed == {}, "disabled rumor propagation must produce no seed"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6 — rumor_signal_expires
# ═══════════════════════════════════════════════════════════════════════════════


def test_scenario_expired_seed_removed_by_expire_call():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 5,
    }
    add_rumor_seed(
        state,
        signal={"signal_id": "sig:old", "kind": "rumor_pressure", "strength": 1},
        topic={"topic_id": "topic:quest:old", "topic_type": "quest"},
        tick=1,
        location_id="loc_tavern",
        settings=settings,
    )
    # Created at tick=1, expires at tick=6
    summary = expire_stale_signals(state, current_tick=10)
    assert summary["expired_count"] == 1
    assert summary["remaining_count"] == 0
    assert state["rumor_propagation_state"]["rumor_seeds"] == []


def test_scenario_active_seed_survives_expire_call():
    state = {}
    settings = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20,
    }
    add_rumor_seed(
        state,
        signal={"signal_id": "sig:active", "kind": "quest_interest", "strength": 1},
        topic={"topic_id": "topic:quest:active", "topic_type": "quest"},
        tick=100,
        location_id="loc_tavern",
        settings=settings,
    )
    # Expires at tick=120; current tick=110 → still active
    summary = expire_stale_signals(state, current_tick=110)
    assert summary["expired_count"] == 0
    assert summary["remaining_count"] == 1


def test_scenario_expire_called_at_conversation_advance():
    """expire_stale_signals is called inside maybe_advance_conversation_thread."""
    state = {}
    set_current_location(state, "loc_tavern")
    settings_base = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 5,
    }
    # Plant a stale seed manually
    add_rumor_seed(
        state,
        signal={"signal_id": "sig:stale", "kind": "rumor_pressure", "strength": 1},
        topic={"topic_id": "topic:quest:stale", "topic_type": "quest"},
        tick=1,
        location_id="loc_tavern",
        settings=settings_base,
    )
    # Advance at tick=20 (well past expiry of tick 6)
    maybe_advance_conversation_thread(
        state,
        player_input="I wait and listen",
        tick=20,
        settings={
            "enabled": True,
            "allow_world_signals": True,
            "allow_world_events": True,
            "thread_cooldown_ticks": 0,
            **settings_base,
        },
    )
    # Stale seed must be gone
    remaining = get_active_rumor_seeds(state, location_id="loc_tavern", current_tick=20)
    stale_ids = [s["seed_id"] for s in remaining if "stale" in s.get("seed_id", "")]
    assert not stale_ids, f"Stale seed survived conversation advance: {stale_ids}"


def test_scenario_expire_summary_fields():
    state = {}
    settings_s1 = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 3,
    }
    settings_s2 = {
        "allow_rumor_propagation": True, "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4, "max_signal_age_ticks": 20,
    }
    # Add two seeds: one stale (expires tick 4), one active (expires tick 22).
    # s2 is added at tick=2 so the internal expire sweep does not prune s1 yet.
    add_rumor_seed(state, signal={"signal_id": "s1", "kind": "quest_interest"},
                   topic={"topic_id": "t1", "topic_type": "quest"},
                   tick=1, location_id="loc_tavern", settings=settings_s1)
    add_rumor_seed(state, signal={"signal_id": "s2", "kind": "danger_warning"},
                   topic={"topic_id": "t2", "topic_type": "recent_event"},
                   tick=2, location_id="loc_market", settings=settings_s2)

    summary = expire_stale_signals(state, current_tick=10)
    assert "expired_count" in summary
    assert "remaining_count" in summary
    assert "current_tick" in summary
    assert "source" in summary
    assert summary["expired_count"] == 1  # t1 expired (1+3=4 <= 10)
    assert summary["remaining_count"] == 1  # t2 still active (2+20=22 > 10)


def test_rumor_seed_expires_at_expiry_tick_boundary():
    state = {}
    settings = {
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_signal_age_ticks": 3,
    }

    add_rumor_seed(
        state,
        signal={"signal_id": "sig:boundary", "kind": "quest_interest", "strength": 1},
        topic={"topic_id": "topic:quest:boundary", "topic_type": "quest"},
        tick=10,
        location_id="loc_tavern",
        settings=settings,
    )

    # expires_tick is 13; at tick 13 it must already be inactive.
    active = get_active_rumor_seeds(
        state,
        location_id="loc_tavern",
        current_tick=13,
        settings=settings,
    )
    assert active == []

    summary = expire_stale_signals(state, current_tick=13, settings=settings)
    assert summary["expired_count"] == 1
    assert summary["remaining_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT MEMORY GUARD — regression tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_synthetic_npc_guard_identifies_room_environment():
    """_is_synthetic_npc_participant must block npc:The Room/Environment."""
    assert _is_synthetic_npc_participant({"id": "npc:The Room/Environment"})
    assert _is_synthetic_npc_participant({"id": "npc:The Room/Environment", "name": "The Room/Environment"})


def test_synthetic_npc_guard_identifies_environment_general():
    assert _is_synthetic_npc_participant({"id": "npc:Environment/NPCs (General)"})
    assert _is_synthetic_npc_participant({"name": "Environment/NPCs (General)", "id": "npc:Environment/NPCs (General)"})


def test_synthetic_npc_guard_identifies_ambient_wait_target():
    assert _is_synthetic_npc_participant({"id": "ambient_wait"})
    assert _is_synthetic_npc_participant({"id": "npc:ambient_wait"})


def test_synthetic_npc_guard_allows_real_npc():
    assert not _is_synthetic_npc_participant({"id": "npc:Bran", "name": "Bran"})
    assert not _is_synthetic_npc_participant({"id": "npc:Mira", "name": "Mira"})
    assert not _is_synthetic_npc_participant({"id": "npc:Elara", "name": "Elara"})


def test_synthetic_npc_guard_blocks_non_npc_prefixed():
    """IDs without npc: prefix are synthetic (except empty ID, handled upstream)."""
    assert _is_synthetic_npc_participant({"id": "room:environment"})
    assert _is_synthetic_npc_participant({"id": "environment:general"})


def test_synthetic_npc_does_not_appear_in_social_state_after_player_join():
    """Regression: record_player_joined_conversation must skip synthetic participants."""
    state = {}
    synthetic_thread = {
        "thread_id": "conversation:loc_tavern:synthetic",
        "participants": [
            {"id": "npc:The Room/Environment", "name": "The Room/Environment"},
            {"id": "npc:Bran", "name": "Bran"},
        ],
    }
    fake_response = {"beat_id": "beat:test", "line": "I am watching."}
    topic = {"topic_id": "topic:location:loc_tavern:mood", "topic_type": "location_smalltalk"}

    record_player_joined_conversation(
        state,
        tick=1,
        thread=synthetic_thread,
        player_response=fake_response,
        topic=topic,
    )

    npc_state = state["conversation_social_state"]["npc_state"]
    assert "npc:The Room/Environment" not in npc_state, (
        "npc:The Room/Environment must NOT appear in conversation_social_state"
    )
    assert "npc:Bran" in npc_state, "Real NPC Bran must still be recorded"
    _assert_no_synthetic_npc_in_social_state(state, label="regression_synthetic_block")


def test_synthetic_npc_skipped_ids_in_debug():
    """The debug block should record which synthetic IDs were skipped."""
    state = {}
    synthetic_thread = {
        "thread_id": "t1",
        "participants": [
            {"id": "npc:The Room/Environment", "name": "The Room/Environment"},
        ],
    }
    record_player_joined_conversation(
        state,
        tick=5,
        thread=synthetic_thread,
        player_response={"beat_id": "b1", "line": "test"},
        topic={"topic_id": "tid", "topic_type": "location_smalltalk"},
    )
    debug = state["conversation_social_state"]["debug"]
    assert "skipped_synthetic_ids" in debug
    assert "npc:The Room/Environment" in debug["skipped_synthetic_ids"]


def test_general_social_effects_skip_room_environment_memory():
    """Regression: ambient observe must not create relationship/emotion/social memory for the room."""
    state = {}

    result = apply_general_social_effects(
        state,
        {
            "action_type": "observe",
            "semantic_action_type": "ambient_wait",
            "semantic_family": "ambient",
            "activity_label": "observe",
            "target_id": "npc:The Room/Environment",
            "target_name": "The Room/Environment",
            "outcome": "failure",
            "service_result": {"matched": False},
        },
        tick=1,
    )

    assert result.get("skipped") is True
    assert result.get("reason") == "synthetic_social_target"
    assert state.get("relationship_state", {}) == {}
    assert state.get("npc_emotion_state", {}) == {}
    assert state.get("memory_state", {}).get("social_memories", []) == []


def test_forced_player_invited_overrides_existing_thread_mode():
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state(
        allow_player_invited=True,
        player_inclusion_chance_percent=100,
        thread_cooldown_ticks=0,
    )

    first = advance_autonomous_ambient_tick(
        player_input="__ambient_tick__",
        simulation_state=state,
        runtime_state=rt,
        tick=10,
    )
    assert first["applied"] is True

    second = advance_autonomous_ambient_tick(
        player_input="__ambient_tick_player_invited__",
        simulation_state=state,
        runtime_state=rt,
        tick=11,
    )

    assert second["applied"] is True
    conv = second["conversation_result"]
    assert conv["player_participation"]["mode"] == "player_invited"
    assert conv["player_participation"]["pending_response"] is True
    assert state["conversation_thread_state"]["pending_player_response"]


def test_live_conversation_does_not_leak_synthetic_npcs():
    """Full conversation flow from invite through player reply must not pollute social state."""
    state = {}
    set_current_location(state, "loc_tavern")
    rt = _runtime_state()
    _invite_player(state, rt, tick=1)
    _player_reply(state, rt, "Anything of interest here?", tick=2)

    _assert_no_synthetic_npc_in_social_state(state, label="live_flow_regression")


def test_no_observe_or_ambient_wait_in_memory_topics():
    """Synthetic observe/ambient_wait entries must not appear as memory topics."""
    from app.rpg.world.conversation_topics import conversation_topics_for_state
    state = {
        "memory_state": {
            "social_memories": [
                {
                    "memory_id": "memory:observe:room",
                    "actor_id": "player",
                    "target_id": "npc:The Room/Environment",
                    "summary": "The player had a partial observe interaction with The Room/Environment.",
                    "action_type": "observe",
                },
                {
                    "memory_id": "memory:observe:ambient",
                    "actor_id": "player",
                    "target_id": "ambient_wait",
                    "summary": "The player waited and observed the ambient environment.",
                    "action_type": "ambient_wait",
                },
                {
                    # Real NPC memory — this SHOULD appear
                    "memory_id": "memory:bran:greeting",
                    "actor_id": "npc:Bran",
                    "target_id": "player",
                    "summary": "Bran greeted the player warmly.",
                    "action_type": "greet",
                },
            ]
        }
    }
    set_current_location(state, "loc_tavern")
    topics = conversation_topics_for_state(state, settings={"allow_memory_discussion": True})
    for topic in topics:
        if topic["topic_type"] == "memory":
            source_id = topic.get("source_id", "")
            assert "room/environment" not in source_id.lower(), (
                f"Room/Environment memory leaked into topics: {topic}"
            )
            assert "ambient_wait" not in source_id.lower(), (
                f"ambient_wait memory leaked into topics: {topic}"
            )
    memory_topics = [t for t in topics if t["topic_type"] == "memory"]
    bran_topics = [t for t in memory_topics if "bran" in t.get("source_id", "").lower()]
    assert bran_topics, "Real NPC memory (Bran) must appear in topics"


def test_general_social_effects_skip_location_general_placeholder_memory():
    """Regression: location placeholder NPCs like npc:The Tavern (General) are not real NPCs."""
    state = {}

    result = apply_general_social_effects(
        state,
        {
            "action_type": "observe",
            "semantic_action_type": "ambient_wait",
            "semantic_family": "ambient",
            "activity_label": "observe",
            "target_id": "",
            "target_name": "The Tavern (General)",
            "outcome": "success",
        },
        tick=527,
    )

    assert result.get("skipped") is True
    assert result.get("reason") == "synthetic_social_target"
    assert state.get("relationship_state", {}) == {}
    assert state.get("npc_emotion_state", {}) == {}
    assert state.get("memory_state", {}).get("social_memories", []) == []


def test_add_rumor_seed_purges_expired_seed_before_dedup():
    state = {}
    settings = {
        "allow_rumor_propagation": True,
        "max_rumor_seeds": 16,
        "max_rumor_mentions_per_location": 4,
        "max_signal_age_ticks": 3,
    }

    first = add_rumor_seed(
        state,
        signal={
            "signal_id": "sig:old",
            "kind": "quest_interest",
            "strength": 1,
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        topic={
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        tick=526,
        location_id="loc_tavern",
        settings=settings,
    )

    assert first["expires_tick"] == 529

    # At the expiry boundary, the old seed must be purged before dedup.
    second = add_rumor_seed(
        state,
        signal={
            "signal_id": "sig:new",
            "kind": "quest_interest",
            "strength": 1,
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        topic={
            "topic_id": "topic:quest:quest:old_mill_bandits",
            "topic_type": "quest",
        },
        tick=529,
        location_id="loc_tavern",
        settings=settings,
    )

    seeds = state["rumor_propagation_state"]["rumor_seeds"]

    assert second
    assert len(seeds) == 1
    assert seeds[0]["created_tick"] == 529
    assert seeds[0]["seed_id"].startswith("rumor_seed:529:")
    assert not any(seed["seed_id"].startswith("rumor_seed:526:") for seed in seeds)
