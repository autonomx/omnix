"""Requests a player makes that change their own state: quests, skill practice, quest progress (no database)."""
from __future__ import annotations

from app.apps.rpg.rules.economy.service_effects import apply_service_purchase_result
from app.apps.rpg.rules.survival_tick_runtime import classify_survival_tick_context
from app.apps.rpg.narration.narrative_engine import AuthorityClass, EvidenceRecord, VisibilityClass
from app.apps.rpg.narration.narrative_engine.evidence import (
    EvidenceAccessContext,
    EvidenceBroker,
    EvidenceQuery,
    InMemoryEvidenceSource,
)
from app.apps.rpg.narration.narrative_engine.shadow import runtime_evidence
from app.apps.rpg.session.player_requests import (
    PRACTICE_SKILL_XP,
    advance_quests_on_arrival,
    apply_player_requests,
    describe_player_events,
    has_player_requests,
)
from app.apps.rpg.session.public_state_bridge import (
    count_player_turn,
    hydrate_simulation_player,
    project_authoritative_player,
)


def _state() -> dict:
    return {
        "player_state": {
            "skills": {"swordsmanship": {"xp": 0, "level": 0, "xp_to_next": 25}, "stealth": {"xp": 0, "level": 0}},
            "inventory_state": {"items": [], "currency": {"gold": 0, "silver": 2, "copper": 0}},
            "currency": {"gold": 0, "silver": 2, "copper": 0},
        },
        "quest_state": {"quests": [
            {"id": "quest:tide", "title": "First Tide", "status": "active",
             "locations": ["location:strand", "location:lamp"], "visited_locations": ["location:strand"],
             "rewards": ["item:shard", "20 silver"]},
            {"id": "quest:bell", "title": "The Drowned Bell", "status": "available", "locations": []},
        ]},
        "world_model": {"items": [{"id": "item:shard", "name": "Sea Shard", "type": "relic"}]},
    }


def _quest(state: dict, quest_id: str) -> dict:
    return next(quest for quest in state["quest_state"]["quests"] if quest["id"] == quest_id)


def test_accepting_a_named_quest_makes_it_active() -> None:
    state = _state()
    assert has_player_requests(state, "I accept the quest of the Drowned Bell")
    assert _quest(state, "quest:bell")["status"] == "available"  # deciding changes nothing
    events = apply_player_requests(state, "I accept the quest of the Drowned Bell")
    assert events[0]["kind"] == "quest_accepted" and _quest(state, "quest:bell")["status"] == "active"
    assert apply_player_requests(state, "I take on the Drowned Bell quest")[0]["kind"] == "quest_already_active"


def test_talk_of_quests_without_taking_one_changes_nothing() -> None:
    state = _state()
    assert apply_player_requests(state, "What quest is the warden on?") == []
    assert apply_player_requests(state, "I start walking along the strand") == []


def test_practising_a_skill_earns_its_experience() -> None:
    state = _state()
    events = apply_player_requests(state, "Practice swordsmanship with a careful drill")
    assert events == [{"kind": "skill_practised", "skill_id": "swordsmanship", "xp_gained": PRACTICE_SKILL_XP,
                       "level_before": 0, "level": 0, "level_ups": []}]
    assert state["player_state"]["skills"]["swordsmanship"]["xp"] == PRACTICE_SKILL_XP
    assert state["player_state"]["skills"]["stealth"]["xp"] == 0
    assert apply_player_requests(state, "Practice juggling") == []


def test_reaching_the_last_place_completes_the_quest_and_pays_it() -> None:
    state = _state()
    events = advance_quests_on_arrival(state, "location:lamp")
    assert events[0]["kind"] == "quest_completed" and events[0]["items"] == ["Sea Shard"]
    assert _quest(state, "quest:tide")["status"] == "completed"
    assert state["player_state"]["currency"] == {"gold": 2, "silver": 2, "copper": 0}  # 2 silver and 20 more, carried over
    assert [item["name"] for item in state["player_state"]["inventory_state"]["items"]] == ["Sea Shard"]
    assert advance_quests_on_arrival(state, "location:lamp") == []  # paid once


def test_survival_tick_reads_whole_words() -> None:
    assert classify_survival_tick_context(player_input="I search the forest")["reason"] == "standard_turn"
    assert classify_survival_tick_context(player_input="What a great view")["skip_tick"] is False
    assert classify_survival_tick_context(player_input="I rest by the fire")["reason"] == "rest_turn"
    assert classify_survival_tick_context(player_input="Walking to the lamp")["reason"] == "travel_turn"


def test_a_bought_meal_eases_hunger() -> None:
    state = {**_state(), "survival": {"enabled": True, "hunger": 50, "thirst": 40, "fatigue": 10, "events": []}}
    offer = {"offer_id": "npc:bo:meal", "service_kind": "meal", "label": "A hot meal", "price": {"silver": 1}}
    service_result = {
        "matched": True, "service_kind": "meal", "provider_id": "npc:bo", "selected_offer_id": "npc:bo:meal",
        "offers": [offer], "purchase": {"offer_id": "npc:bo:meal", "price": {"silver": 1},
                                        "resource_changes": {"currency": {"silver": -1}}},
    }
    applied = apply_service_purchase_result(state, service_result, tick=3)
    assert applied["applied"] is True
    assert state["survival"]["hunger"] == 15 and state["survival"]["thirst"] == 40


def test_asking_where_you_stand_reports_it_from_state() -> None:
    state = _state()
    report = apply_player_requests(state, "Check my quests and inventory")[0]
    assert report["kind"] == "status_report" and report["topics"] == ["inventory", "quests"]
    lines = describe_player_events([report])
    assert lines[0] == "You carry nothing; your purse holds 2 silver."
    assert lines[1] == "Active quests: First Tide."
    assert lines[2] == "Quests you could take on: The Drowned Bell."
    # Asking someone about a quest is a conversation, not a status check.
    assert apply_player_requests(state, "What is the quest you spoke of?") == []


def test_turn_events_become_plain_sentences() -> None:
    lines = describe_player_events([
        {"kind": "quest_accepted", "title": "The Drowned Bell", "objective": "Find the bell"},
        {"kind": "skill_practised", "skill_id": "swordsmanship", "xp_gained": 10, "level_before": 0, "level": 1},
        {"kind": "quest_completed", "title": "First Tide", "currency": {"silver": 20, "gold": 0}, "items": ["Sea Shard"]},
    ])
    assert lines == [
        "You take on the quest The Drowned Bell: Find the bell.",
        "Your practice earns 10 experience in swordsmanship. Swordsmanship rises to level 1.",
        "Quest complete: First Tide. You receive 20 silver, Sea Shard.",
    ]


def test_the_turn_outcome_reaches_the_narrator_first() -> None:
    result = {"resolved_result": {"outcome_lines": ["You take on the quest The Drowned Bell."]}, "state_revision": 4}
    outcome = next(record for record in runtime_evidence(result) if record.evidence_id == "runtime:turn:outcome")
    assert outcome.authority is AuthorityClass.CONFIRMED_TURN and outcome.content == "You take on the quest The Drowned Bell."
    # Ranked ahead of canon that shares more words with the player's input.
    canon = tuple(
        EvidenceRecord(evidence_id=f"canon:{index}", content="The drowned bell quest legend of the bell tower",
                       authority=AuthorityClass.OBJECTIVE_CANON, visibility=VisibilityClass.PUBLIC)
        for index in range(12)
    )
    retrieved = EvidenceBroker([InMemoryEvidenceSource((*canon, outcome))]).retrieve(
        EvidenceQuery(text="I accept the drowned bell quest", access=EvidenceAccessContext(), limit=4)
    )
    assert retrieved.evidence[0].evidence_id == "runtime:turn:outcome"


def test_the_sheet_keeps_the_hero_name_counts_turns_and_shows_experience() -> None:
    session = {
        "state": {"player": {"name": "Wren", "xp": {"current": 0, "max": 100}}, "turn_count": 2},
        "manifest": {"turn_count": 2},
        "simulation_state": {"player_state": {"name": "Player", "xp": 30, "xp_to_next": 120, "level": 2}},
    }
    session = hydrate_simulation_player(session)
    assert session["simulation_state"]["player_state"]["name"] == "Wren"
    session = project_authoritative_player(session)
    assert session["state"]["player"]["xp"] == {"current": 30, "max": 120} and session["state"]["player"]["level"] == 2
    # Each stage of one turn counts from its own copy of the turn-start session: they agree on one turn.
    def turn_start() -> dict:
        return {**session, "state": dict(session["state"]), "manifest": dict(session["manifest"])}

    dialogue_stage, authoritative_stage = count_player_turn(turn_start()), count_player_turn(turn_start())
    assert dialogue_stage["state"]["turn_count"] == authoritative_stage["state"]["turn_count"] == 3
    assert authoritative_stage["manifest"]["turn_count"] == 3


def test_when_someone_answers_the_narrator_still_tells_what_the_turn_did() -> None:
    from app.apps.rpg.narration.narrative_engine import (
        DeterministicBeatPlanner,
        PresentationProfile,
        TurnPresentationRequest,
    )

    outcome = EvidenceRecord(evidence_id="runtime:turn:outcome", content="You pay 8 copper to Bran for A drink.",
                             authority=AuthorityClass.CONFIRMED_TURN, visibility=VisibilityClass.PLAYER_KNOWN)
    profile = EvidenceRecord(evidence_id="lore:bran", content="Bran keeps the Rusty Flagon.",
                             authority=AuthorityClass.OBJECTIVE_CANON, visibility=VisibilityClass.PUBLIC,
                             entity_refs=("npc:bran",))
    request = TurnPresentationRequest(
        request_id="request:drink", turn_id="turn:3", campaign_id="campaign:test", player_input="buy a drink",
        actor_ids=("npc:bran",), target_actor_id="npc:bran", presentation_profile=PresentationProfile.FAST,
        metadata={"response_mode": "dialogue"},
    )
    plan = DeterministicBeatPlanner().plan(request, (profile, outcome))
    narrator = plan.beats[0]
    assert narrator.speaker_id is None and "runtime:turn:outcome" in narrator.evidence_refs


def _shop_world_state() -> dict:
    state = _state()
    state["player_state"]["location_id"] = "location:market"
    state["player_state"]["inventory_state"]["items"] = [
        {"item_id": "item:dagger", "name": "Iron Dagger", "qty": 1},
        {"item_id": "item:bread", "name": "Lantern Bread", "qty": 2, "category": "food"},
        {"item_id": "item:shard", "name": "Sea Shard", "qty": 1},
    ]
    state["world_model"] = {
        "items": [],
        "providers": {"npc:brin": {"provider_id": "npc:brin", "provider_name": "Brin Gear", "location_id": "location:market",
                                    "service_kinds": ["shop_goods"]}},
        "offers": {"npc:brin": [{"label": "Lantern Bread", "price": {"copper": 8}}]},
    }
    return state


def test_a_shopkeeper_buys_what_the_player_carries() -> None:
    state = _shop_world_state()
    # Goods the shop trades in fetch half its price; other goods a token sum.
    assert apply_player_requests(state, "I sell a Lantern Bread to Brin Gear")[0] == {
        "kind": "item_sold", "item": "Lantern Bread", "buyer": "Brin Gear", "copper": 4}
    sold = apply_player_requests(state, "I sell my Iron Dagger")[0]
    assert sold["copper"] == 5
    player = state["player_state"]
    assert [(item["name"], item["qty"]) for item in player["inventory_state"]["items"]] == [("Lantern Bread", 1), ("Sea Shard", 1)]
    assert player["currency"] == player["inventory_state"]["currency"] == {"gold": 0, "silver": 2, "copper": 9}
    assert describe_player_events([sold]) == ["You sell the Iron Dagger to Brin Gear for 5 copper."]


def test_some_sales_do_not_happen() -> None:
    state = _shop_world_state()
    # A quest's reward is a keepsake; what the player does not carry cannot be sold; nobody buys elsewhere.
    assert apply_player_requests(state, "I sell the Sea Shard")[0]["reason"] == "keepsake"
    assert apply_player_requests(state, "I sell my Moon Lantern")[0]["reason"] == "not_carried"
    state["player_state"]["location_id"] = "location:road"
    assert apply_player_requests(state, "I sell my Iron Dagger")[0]["reason"] == "no_buyer_here"
    assert len(state["player_state"]["inventory_state"]["items"]) == 3


def test_what_is_put_down_lies_there_until_picked_up() -> None:
    state = _shop_world_state()
    dropped = apply_player_requests(state, "I drop one Lantern Bread on the ground")
    assert dropped == [{"kind": "item_dropped", "item": "Lantern Bread", "qty": 1}]
    assert ("Lantern Bread", 1) in [(item["name"], item["qty"]) for item in state["player_state"]["inventory_state"]["items"]]
    assert [item["name"] for item in state["world_items"]["by_location"]["location:market"]] == ["Lantern Bread"]
    # Elsewhere it is not there to take.
    state["player_state"]["location_id"] = "location:road"
    assert apply_player_requests(state, "I pick up the Lantern Bread") == [{"kind": "pick_up_refused", "reason": "not_here"}]
    state["player_state"]["location_id"] = "location:market"
    assert apply_player_requests(state, "I pick up the Lantern Bread")[0]["kind"] == "item_picked_up"
    assert ("Lantern Bread", 2) in [(item["name"], item["qty"]) for item in state["player_state"]["inventory_state"]["items"]]
    assert state["world_items"]["by_location"]["location:market"] == []
    assert describe_player_events(dropped) == ["You put down the Lantern Bread; it lies here now."]
    # Other meanings of the words do nothing here.
    assert apply_player_requests(state, "I drop by the guild hall") == []
    assert apply_player_requests(state, "I take on the quest of the Drowned Bell")[0]["kind"] == "quest_accepted"
