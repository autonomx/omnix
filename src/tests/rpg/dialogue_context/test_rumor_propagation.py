from app.rpg.dialogue_context.rumors import propagate_rumor
from app.rpg.lore.state import get_lore_entry, upsert_lore_entry
from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def test_rumor_spreads_to_explicit_hearer_without_promoting_truth():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
        },
    )

    result = propagate_rumor(
        simulation_state,
        speaker_id="bran",
        lore_id="lore:red_sashes",
        summary="The Red Sashes are active again.",
        explicit_hearers=["mira"],
        turn_index=1,
    )

    memories = retrieve_causal_memories(simulation_state, "mira", tags=["rumor"])
    assert result["ok"] is True
    assert result["hearers"] == ["mira"]
    assert memories
    assert memories[0]["event_id"] == result["event_id"]
    assert get_lore_entry(simulation_state, "lore:red_sashes")["truth_status"] == "rumor"
    assert result["truth_promoted"] is False


def test_rumor_does_not_spread_to_speaker():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:x", "title": "X", "truth_status": "rumor"})

    result = propagate_rumor(
        simulation_state,
        speaker_id="bran",
        lore_id="lore:x",
        summary="X is happening.",
        explicit_hearers=["bran", "mira"],
    )

    assert result["hearers"] == ["mira"]


def test_rumor_missing_lore_rejected():
    result = propagate_rumor(
        {},
        speaker_id="bran",
        lore_id="lore:missing",
        summary="Missing lore rumor.",
        explicit_hearers=["mira"],
    )

    assert result["ok"] is False
    assert result["reason"] == "lore_missing"


def test_rumor_uses_spatial_audibility_when_no_explicit_hearers():
    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
        },
    )

    result = propagate_rumor(
        simulation_state,
        speaker_id="bran",
        lore_id="lore:red_sashes",
        summary="The Red Sashes are active again.",
        turn_index=1,
    )

    assert result["ok"] is True
    assert "bran" not in result["hearers"]
    assert len(result["hearers"]) <= result["bounded"]["max_hearers"]


def test_propagated_rumor_memory_preserves_lore_facts():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
        },
    )

    result = propagate_rumor(
        simulation_state,
        speaker_id="bran",
        lore_id="lore:red_sashes",
        summary="The Red Sashes are active again.",
        explicit_hearers=["mira"],
        turn_index=1,
    )

    memories = retrieve_causal_memories(simulation_state, "mira", tags=["rumor"])
    assert result["ok"] is True
    assert memories
    assert memories[0]["event_id"] == result["event_id"]
    assert memories[0]["facts"]["lore_id"] == "lore:red_sashes"
    assert memories[0]["facts"]["rumor"] is True