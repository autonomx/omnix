from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.rpg.session.genesis.world_forge_profile_generation import (
    STANDARD_DOMAIN_IDS,
    default_profile_registry,
)
from app.rpg.worlds import library_service


class _WorldLibrary:
    def list_topics(self, context: object, world_id: str) -> list[dict]:
        del context, world_id
        return []

    def list_generation_runs(
        self,
        context: object,
        *,
        world_id: str,
        limit: int,
    ) -> list[dict]:
        del context, world_id, limit
        return []


class _Work:
    world_library = _WorldLibrary()

    def rollback(self) -> None:
        return None


@contextmanager
def _unit_of_work(database: object):
    del database
    yield _Work()


def _approved_world() -> dict[str, object]:
    profile = default_profile_registry().resolve("fallout style")
    assert profile is not None
    return {
        "id": "world:waste",
        "title": "Wasted Coast",
        "description": "A nuclear coastal wasteland governed by ferry settlements.",
        "genre": "fallout style",
        "tone": "survival satire",
        "seed": 17,
        "draft_revision": 1,
        "metadata": {
            "campaign_template": "open_world",
            "campaign_mode": "persistent_living_world",
            "genre_profile_binding": {
                "status": "ready",
                "requested_genre": "fallout style",
                "normalized_genre": "post_apocalyptic",
                "source": "registry",
                "generated": False,
                "profile_id": profile.profile_id,
                "profile_version": profile.version,
                "profile_hash": profile.content_hash,
                "approved_profile_hash": profile.content_hash,
                "profile_revision": 1,
                "profile": profile.as_dict(),
            },
        },
    }


def _route() -> SimpleNamespace:
    return SimpleNamespace(
        requested_provider="deterministic",
        requested_model="deterministic",
        provider="deterministic",
        model="deterministic",
        source="explicit",
        is_deterministic=True,
    )


def _install_common(monkeypatch, world: dict[str, object], captured: dict[str, object]) -> None:
    monkeypatch.setattr(library_service, "bootstrap_local_tenant", lambda value: object())
    monkeypatch.setattr(library_service, "unit_of_work", _unit_of_work)
    monkeypatch.setattr(
        library_service,
        "require_world_writable",
        lambda work, context, world_id: world,
    )
    monkeypatch.setattr(library_service, "resolve_world_forge_route", lambda *_: _route())
    monkeypatch.setattr(
        library_service,
        "resolve_generation_scope",
        lambda graph, **kwargs: (
            tuple(node.topic_id for node in graph.nodes),
            (),
            {"mode": "all"},
        ),
    )

    def start_world_generation(**kwargs):
        captured.update(kwargs)
        return {
            "plan": {"new_job_ids": [], "topic_ids": []},
            "progress": {"active_topic_ids": []},
        }

    monkeypatch.setattr(
        library_service,
        "start_world_generation",
        start_world_generation,
    )
    monkeypatch.setattr(
        library_service,
        "kick_world_generation_worker",
        lambda **kwargs: False,
    )


def test_deterministic_library_generation_uses_approved_standard_profile_graph(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    world = _approved_world()
    _install_common(monkeypatch, world, captured)

    result = library_service.start_world_library_generation(
        "world:waste",
        provider_route="deterministic",
        model="deterministic",
        kick_worker=False,
    )

    graph = captured["graph"]
    generation_context = captured["generation_context"]
    assert graph.graph_version == "rpg_profile_topic_graph_v2"
    assert graph.metadata["genre_profile_id"] == "post_apocalyptic"
    assert set(STANDARD_DOMAIN_IDS).issubset(graph.node_map())
    assert graph.node_map()["actors"].category == "actors"
    assert graph.node_map()["places"].metadata["presentation"]["page_kind"] == "collection"
    assert graph.node_map()["actors"].metadata["presentation"]["image_role"] == "portrait"
    assert generation_context["approved_profile_hash"] == graph.metadata[
        "resolved_profile_hash"
    ]
    assert result["approved_profile_hash"] == graph.metadata["resolved_profile_hash"]


def test_world_content_generation_rejects_unapproved_profile(monkeypatch) -> None:
    captured: dict[str, object] = {}
    world = _approved_world()
    binding = world["metadata"]["genre_profile_binding"]  # type: ignore[index]
    binding["approved_profile_hash"] = ""  # type: ignore[index]
    _install_common(monkeypatch, world, captured)

    with pytest.raises(ValueError, match="world_profile_approval_required"):
        library_service.start_world_library_generation(
            "world:waste",
            provider_route="deterministic",
            model="deterministic",
            kick_worker=False,
        )

    assert captured == {}
