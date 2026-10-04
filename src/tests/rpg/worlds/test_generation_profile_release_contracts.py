from __future__ import annotations

from app.rpg.worlds.generation_profile_release_contracts import (
    require_profile_release_contracts,
)


def _nodes(*topic_ids: str) -> list[dict]:
    return [
        {
            "topic_id": topic_id,
            "title": topic_id.title(),
            "category": "lore",
            "dependencies": [],
            "generator_role": "world_forge",
            "metadata": {},
        }
        for topic_id in topic_ids
    ]


def test_modern_profile_requires_starting_market_and_starter_bubble() -> None:
    graph = {
        "graph_version": "rpg_profile_topic_graph_v2",
        "metadata": {"genre_profile_id": "fantasy"},
        "nodes": _nodes(
            "regions",
            "places",
            "actors",
            "equipment_vehicles",
        ),
    }

    result = require_profile_release_contracts(graph)

    market = result["metadata"]["starting_market_contract"]
    bubble = result["metadata"]["starter_bubble_contract"]
    assert market["required"] is True
    assert market["required_before_launch"] is True
    assert market["domain_ids"] == [
        "places",
        "actors",
        "equipment_vehicles",
    ]
    assert bubble["required"] is True
    assert bubble["required_before_launch"] is True
    assert bubble["domain_ids"] == [
        "regions",
        "places",
        "actors",
        "equipment_vehicles",
    ]


def test_partial_modern_profile_only_requires_supported_contracts() -> None:
    graph = {
        "graph_version": "rpg_profile_topic_graph_v2",
        "metadata": {"genre_profile_id": "market_only"},
        "nodes": _nodes("places", "actors", "equipment_vehicles"),
    }

    result = require_profile_release_contracts(graph)

    assert result["metadata"]["starting_market_contract"]["required"] is True
    assert "starter_bubble_contract" not in result["metadata"]


def test_legacy_graph_is_not_silently_upgraded() -> None:
    graph = {
        "graph_version": "legacy-v1",
        "metadata": {},
        "nodes": _nodes(
            "regions",
            "places",
            "actors",
            "equipment_vehicles",
        ),
    }

    result = require_profile_release_contracts(graph)

    assert "starting_market_contract" not in result["metadata"]
    assert "starter_bubble_contract" not in result["metadata"]
