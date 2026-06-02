def _rich_quest_state():
    from app.rpg.quests.givers import accept_quest_offer
    from app.rpg.quests.journal import add_journal_entry_from_objective_result
    from app.rpg.quests.objectives import complete_objective_lifecycle
    from app.rpg.quests.rewards import claim_quest_rewards
    from app.rpg.quests.rumors import back_rumor_with_evidence, convert_rumor_to_quest_offer, register_rumor

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 2}}}}
    register_rumor(
        state,
        rumor_id="rumor:old_mill_bandit",
        summary="Travelers whisper about a bandit near the old mill road.",
        quest_id="quest:clear_the_road",
        giver_id="npc:bran",
        location_id="location:rusty_flagon",
        turn_index=1,
    )
    back_rumor_with_evidence(
        state,
        rumor_id="rumor:old_mill_bandit",
        evidence_id="evidence:bran:witness",
        source_id="npc:bran",
        summary="Bran confirms the road is dangerous.",
        turn_index=2,
    )
    convert_rumor_to_quest_offer(state, rumor_id="rumor:old_mill_bandit", turn_index=3)
    accept_quest_offer(state, giver_id="npc:bran", quest_id="quest:clear_the_road", turn_index=4)
    objective_result = complete_objective_lifecycle(
        state,
        quest_id="quest:clear_the_road",
        objective_id="objective:defeat_bandit",
        turn_index=8,
    )
    add_journal_entry_from_objective_result(
        state,
        objective_result,
        turn_index=8,
        what_i_learned="The old road is safe enough for trade again.",
    )
    claim_quest_rewards(state, quest_id="quest:clear_the_road", turn_index=9)
    return state


def test_ci_phase3_quest_persistence_snapshot_captures_all_quest_substates():
    from app.rpg.quests.persistence import build_quest_persistence_snapshot

    state = _rich_quest_state()
    snapshot = build_quest_persistence_snapshot(state)

    assert snapshot["source"] == "deterministic_quest_persistence"
    assert snapshot["version"] == 1
    assert snapshot["quest_state"]["quests"]["quest:clear_the_road"]["status"] == "completed"
    assert snapshot["quest_giver_state"]["givers"]["npc:bran"]["offers"]["quest:clear_the_road"]["status"] == "accepted"
    assert snapshot["journal_state"]["entries"][0]["source"] == "deterministic_quest_journal_runtime"
    assert snapshot["rumor_state"]["rumors"]["rumor:old_mill_bandit"]["status"] == "converted"
    assert snapshot["reward_state"]["log"][0]["source"] == "deterministic_quest_reward_rules"
    assert snapshot["summary"] == {
        "quest_count": 1,
        "journal_entry_count": 1,
        "rumor_count": 1,
        "reward_log_count": 1,
    }


def test_ci_phase3_quest_persistence_roundtrip_restores_equivalent_snapshot():
    from app.rpg.quests.persistence import (
        assert_quest_persistence_roundtrip,
        build_quest_persistence_snapshot,
        restore_quest_persistence_snapshot,
    )

    state = _rich_quest_state()
    snapshot = build_quest_persistence_snapshot(state)
    restored = {}
    result = restore_quest_persistence_snapshot(restored, snapshot)
    roundtrip = assert_quest_persistence_roundtrip(state)

    assert result["ok"] is True
    assert result["reason"] == "quest_persistence_snapshot_restored"
    assert result["source"] == "deterministic_quest_persistence"
    assert result["snapshot"] == snapshot
    assert build_quest_persistence_snapshot(restored) == snapshot
    assert roundtrip["ok"] is True
    assert roundtrip["reason"] == "quest_persistence_roundtrip_matched"


def test_ci_phase3_quest_persistence_rejects_invalid_snapshots_without_mutation():
    from copy import deepcopy

    from app.rpg.quests.persistence import restore_quest_persistence_snapshot

    state = _rich_quest_state()
    before = deepcopy(state)
    bad_source = restore_quest_persistence_snapshot(state, {"source": "wrong", "version": 1})
    bad_version = restore_quest_persistence_snapshot(state, {"source": "deterministic_quest_persistence", "version": 999})

    assert bad_source["ok"] is False
    assert bad_source["reason"] == "invalid_snapshot_source"
    assert bad_source["source"] == "deterministic_quest_persistence"
    assert bad_version["ok"] is False
    assert bad_version["reason"] == "unsupported_snapshot_version"
    assert state == before


def test_ci_phase3_quest_persistence_helpers_are_exported():
    from app.rpg import quests

    assert quests.build_quest_persistence_snapshot
    assert quests.restore_quest_persistence_snapshot
    assert quests.assert_quest_persistence_roundtrip
