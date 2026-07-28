from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.library_service import _world_generation_context
from app.rpg.worlds.generation_scope import resolve_generation_scope


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="scope-test-v1",
        campaign_template="fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode("realm", "Realm", "lore"),
            CampaignTopicNode("regions", "Regions", "regions", ("realm",)),
            CampaignTopicNode("factions", "Factions", "factions", ("regions",)),
            CampaignTopicNode("locations", "Locations", "locations", ("regions", "factions")),
        ),
    )


def test_selected_scope_includes_dependency_closure_without_forcing_dependencies() -> None:
    targets, forced, scope = resolve_generation_scope(
        _graph(),
        scope={"mode": "selected", "topic_ids": ["locations"]},
        strategy="force",
        topic_rows=[],
        latest_run=None,
        replace_locked=False,
    )

    assert targets == ("realm", "regions", "factions", "locations")
    assert forced == ("locations",)
    assert scope["topic_ids"] == ["locations"]
    assert scope["resolved_topic_ids"] == list(targets)


def test_stale_and_failed_scopes_resolve_from_durable_status() -> None:
    stale_targets, _, stale_scope = resolve_generation_scope(
        _graph(),
        scope={"mode": "stale"},
        strategy="reuse_unchanged",
        topic_rows=[{"topic_id": "factions", "status": "stale"}],
        latest_run=None,
    )
    failed_targets, _, failed_scope = resolve_generation_scope(
        _graph(),
        scope={"mode": "failed"},
        strategy="reuse_unchanged",
        topic_rows=[],
        latest_run={"progress": {"failed_topic_ids": ["locations"]}},
    )

    assert stale_targets == ("realm", "regions", "factions")
    assert stale_scope["mode"] == "stale"
    assert failed_targets == ("realm", "regions", "factions", "locations")
    assert failed_scope["mode"] == "failed"


def test_forced_locked_topic_requires_explicit_replacement() -> None:
    with pytest.raises(ValueError, match="generation_topics_locked:factions"):
        resolve_generation_scope(
            _graph(),
            scope={"mode": "selected", "topic_ids": ["factions"]},
            strategy="force",
            topic_rows=[
                {
                    "topic_id": "factions",
                    "status": "ready",
                    "source": "manual",
                    "provenance": {"authoring": {"generation_lock": True}},
                }
            ],
            latest_run=None,
            replace_locked=False,
        )


def test_generation_context_preserves_authored_world_brief() -> None:
    route = type(
        "Route",
        (),
        {
            "requested_provider": "lmstudio",
            "requested_model": "local-model",
            "source": "settings_control_center",
        },
    )()

    context = _world_generation_context(
        {
            "title": "Fallout",
            "description": "A retro-futuristic nuclear wasteland of Vaults and mutants.",
            "genre": "classic_fantasy",
            "tone": "heroic adventure",
            "metadata": {"campaign_template": "classic_fantasy"},
        },
        starting_location="",
        background_expansion=True,
        route=route,
    )

    assert context["world_brief"] == {
        "title": "Fallout",
        "description": "A retro-futuristic nuclear wasteland of Vaults and mutants.",
        "source_mode": "",
        "genre": "classic_fantasy",
        "tone": "heroic adventure",
        "campaign_template": "classic_fantasy",
    }
