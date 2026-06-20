from app.rpg.session.genesis import (
    CAMPAIGN_GENESIS_CONTRACT_VERSION,
    GENESIS_COMPILER_VERSION,
    CampaignGenesisContract,
    GenesisDrivers,
    GenesisIdentity,
    GenesisInitialStats,
    GenesisMotivation,
    GenesisSystemOptions,
    GenesisTalent,
    GenesisWorldOptions,
    bootstrap_session_from_compiled_genesis,
    compile_campaign_genesis,
    genesis_contract_hash,
)


def _sample_contract() -> CampaignGenesisContract:
    return CampaignGenesisContract(
        identity=GenesisIdentity(
            name="Mira",
            pronouns="she/her",
            background="wanderer",
            origin="river_district",
            power_source="mundane",
        ),
        drivers=GenesisDrivers(
            archetype="ranger",
            motivation=GenesisMotivation(primary="protect_home", target="river_district", intensity=75),
            talents=[GenesisTalent(id="fieldcraft", rank=2), GenesisTalent(id="contacts", rank=1)],
            values=["family", "freedom"],
        ),
        initial_stats=GenesisInitialStats(perception=12, survival=9),
        starter_gear_tags=["travel_supplies", "survival_tool", "field_notes"],
        world_options=GenesisWorldOptions(
            world_profile="harsh_frontier",
            starting_location="northern_watch_post",
            difficulty="harsh",
            world_activity="living_world",
            economy_pressure="strict",
            seed=9137,
        ),
        system_options=GenesisSystemOptions(tts=True, stt=True),
    )


def test_contract_hash_is_stable_for_equivalent_contracts() -> None:
    first = _sample_contract()
    second = CampaignGenesisContract.model_validate(first.model_dump(mode="json"))

    assert first.contract_version == CAMPAIGN_GENESIS_CONTRACT_VERSION
    assert genesis_contract_hash(first) == genesis_contract_hash(second)


def test_compiler_emits_versioned_derived_state() -> None:
    compiled = compile_campaign_genesis(_sample_contract())

    assert compiled["compiler_version"] == GENESIS_COMPILER_VERSION
    assert compiled["compiled_provenance"]["contract_version"] == CAMPAIGN_GENESIS_CONTRACT_VERSION
    assert compiled["compiled_provenance"]["compiler_version"] == GENESIS_COMPILER_VERSION
    assert compiled["compiled_stats"]["perception"] == 12
    assert "active_world" in compiled["compiled_world_traits"]
    assert "scarce_resources" in compiled["compiled_world_traits"]
    assert compiled["compiled_goals"]
    assert [entry["tag"] for entry in compiled["compiled_gear_intents"]] == [
        "travel_supplies",
        "survival_tool",
        "field_notes",
    ]
    assert [entry["source_tag"] for entry in compiled["compiled_starter_loadout"]] == [
        "travel_supplies",
        "survival_tool",
        "field_notes",
    ]


def test_bootstrap_projects_compiled_genesis_without_recompiling() -> None:
    compiled = compile_campaign_genesis(_sample_contract())
    bootstrap = bootstrap_session_from_compiled_genesis(compiled)

    assert bootstrap["provenance"] == compiled["compiled_provenance"]
    assert bootstrap["stats"] == compiled["compiled_stats"]
    assert bootstrap["active_goals"] == compiled["compiled_goals"]
    assert bootstrap["gear_intents"] == compiled["compiled_gear_intents"]
    assert bootstrap["starter_loadout"] == compiled["compiled_starter_loadout"]
