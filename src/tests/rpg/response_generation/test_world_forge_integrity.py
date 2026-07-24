import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_integrity import (
    WorldForgeIntegrityError,
    resolve_reference,
    validate_and_normalize_provider_topic,
)


def _quest_node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="quests",
        title="Quest Catalog",
        category="quests",
        target_count=1,
    )


def _dependencies(*npcs: dict) -> dict[str, GeneratedTopic]:
    return {
        "npcs": GeneratedTopic(topic_id="npcs", entities=tuple(npcs)),
        "locations": GeneratedTopic(
            topic_id="locations",
            entities=(
                {
                    "id": "location:market",
                    "name": "Market",
                    "kind": "location",
                },
            ),
        ),
        "factions": GeneratedTopic(
            topic_id="factions",
            entities=(
                {
                    "id": "faction:wardens",
                    "name": "Wardens",
                    "kind": "faction",
                },
            ),
        ),
    }


def _quest(giver: str) -> GeneratedTopic:
    return GeneratedTopic(
        topic_id="quests",
        entities=(
            {
                "id": "quest:first",
                "name": "First Contract",
                "giver_id": giver,
                "location_ids": ["location:market"],
                "faction_ids": ["faction:wardens"],
                "objectives": ["Investigate the signal"],
                "rewards": ["safe passage"],
                "stakes": "The market loses its only supply route.",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )


def test_unknown_quest_giver_is_not_replaced_by_first_npc() -> None:
    dependencies = _dependencies(
        {"id": "npc:first", "name": "First", "kind": "npc"},
        {"id": "npc:second", "name": "Second", "kind": "npc"},
    )

    with pytest.raises(WorldForgeIntegrityError) as raised:
        validate_and_normalize_provider_topic(
            _quest_node(), _quest("npc:missing"), dependencies
        )

    issue = next(issue for issue in raised.value.issues if issue.field == "giver_id")
    assert issue.code == "unresolved_reference"
    assert issue.supplied_value == "npc:missing"
    assert issue.candidates == ("npc:first", "npc:second")


def test_unique_exact_name_resolves_to_canonical_id() -> None:
    dependencies = _dependencies(
        {"id": "npc:ada", "name": "Ada Voss", "kind": "npc"},
    )

    normalized = validate_and_normalize_provider_topic(
        _quest_node(), _quest("Ada Voss"), dependencies
    )

    assert normalized.entities[0]["giver_id"] == "npc:ada"


def test_ambiguous_exact_name_fails() -> None:
    dependencies = _dependencies(
        {"id": "npc:ada_one", "name": "Ada", "kind": "npc"},
        {"id": "npc:ada_two", "name": "Ada", "kind": "npc"},
    )

    with pytest.raises(WorldForgeIntegrityError) as raised:
        validate_and_normalize_provider_topic(
            _quest_node(), _quest("Ada"), dependencies
        )

    issue = next(issue for issue in raised.value.issues if issue.field == "giver_id")
    assert issue.code == "ambiguous_reference"
    assert issue.candidates == ("npc:ada_one", "npc:ada_two")


def test_declared_alias_resolves() -> None:
    dependencies = _dependencies(
        {"id": "npc:ada", "name": "Ada Voss", "kind": "npc"},
    )

    normalized = validate_and_normalize_provider_topic(
        _quest_node(),
        _quest("the courier"),
        dependencies,
        aliases={"the courier": "npc:ada"},
    )

    assert normalized.entities[0]["giver_id"] == "npc:ada"
    resolutions = normalized.provenance["reference_resolutions"]
    assert any(row["status"] == "alias_resolved" for row in resolutions)


def test_duplicate_entity_ids_fail() -> None:
    topic = GeneratedTopic(
        topic_id="quests",
        entities=(_quest("npc:ada").entities[0], _quest("npc:ada").entities[0]),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )
    dependencies = _dependencies(
        {"id": "npc:ada", "name": "Ada", "kind": "npc"},
    )

    with pytest.raises(WorldForgeIntegrityError) as raised:
        validate_and_normalize_provider_topic(_quest_node(), topic, dependencies)

    assert any(issue.code == "duplicate_entity_id" for issue in raised.value.issues)


def test_resolver_never_selects_first_candidate() -> None:
    resolution = resolve_reference(
        "unknown",
        known={
            "npc:a": {"id": "npc:a", "kind": "npc", "name": "A"},
            "npc:b": {"id": "npc:b", "kind": "npc", "name": "B"},
        },
        allowed_kinds=("npc",),
    )
    assert resolution.status == "unresolved"
    assert resolution.resolved_id is None
