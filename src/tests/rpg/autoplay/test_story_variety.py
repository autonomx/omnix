from tests.rpg.autoplay.seeding import (
    available_campaign_seeds,
    resolve_campaign_seed_name,
    seed_campaign,
)
from tests.rpg.autoplay.story_variety import (
    compute_story_variety_metrics,
    extract_story_signature_from_state,
)


def test_available_campaign_seeds_include_variants():
    seeds = available_campaign_seeds()

    assert "tavern_story_seed" in seeds
    assert "caravan_ambush_seed" in seeds
    assert "missing_apprentice_seed" in seeds
    assert "haunted_mill_seed" in seeds
    assert "noble_blackmail_seed" in seeds


def test_random_campaign_seed_is_reproducible():
    first = resolve_campaign_seed_name("random", random_seed=123)
    second = resolve_campaign_seed_name("random", random_seed=123)

    assert first["resolved_seed"] == second["resolved_seed"]
    assert first["randomized"] is True


def test_different_campaign_seeds_produce_different_story_signatures():
    tavern_state = {}
    caravan_state = {}

    seed_campaign(tavern_state, "tavern_story_seed")
    seed_campaign(caravan_state, "caravan_ambush_seed")

    tavern_signature = extract_story_signature_from_state(tavern_state)
    caravan_signature = extract_story_signature_from_state(caravan_state)

    assert tavern_signature["campaign_title"] != caravan_signature["campaign_title"]
    assert tavern_signature["signature_hash"] != caravan_signature["signature_hash"]
    assert "Bran" in tavern_signature["npc_names"]
    assert "Selka" in caravan_signature["npc_names"]


def test_story_variety_metrics_include_seed_and_hashes():
    state = {}
    seed_campaign(state, "haunted_mill_seed")

    metrics = compute_story_variety_metrics(
        summary={
            "scenario_seed": "haunted_mill_seed",
            "resolved_scenario_seed": "haunted_mill_seed",
            "seed_resolution": {"random_seed": None, "randomized": False},
        },
        state=state,
        transcript=[],
    )

    assert metrics["resolved_seed"] == "haunted_mill_seed"
    assert metrics["story_signature"]["campaign_title"] == "The Haunted Mill"
    assert metrics["story_variety_key"]