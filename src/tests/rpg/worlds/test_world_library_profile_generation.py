from contextlib import contextmanager
from types import SimpleNamespace

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


def test_deterministic_library_generation_uses_resolved_profile_graph(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    world = {
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
        },
    }
    route = SimpleNamespace(
        requested_provider="deterministic",
        requested_model="deterministic",
        provider="deterministic",
        model="deterministic",
        source="explicit",
        is_deterministic=True,
    )

    monkeypatch.setattr(library_service, "bootstrap_local_tenant", lambda value: object())
    monkeypatch.setattr(library_service, "unit_of_work", _unit_of_work)
    monkeypatch.setattr(
        library_service,
        "require_world_writable",
        lambda work, context, world_id: world,
    )
    monkeypatch.setattr(library_service, "resolve_world_forge_route", lambda *_: route)
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

    result = library_service.start_world_library_generation(
        "world:waste",
        provider_route="deterministic",
        model="deterministic",
        kick_worker=False,
    )

    graph = captured["graph"]
    generation_context = captured["generation_context"]
    assert graph.graph_version == "rpg_profile_topic_graph_v1"
    assert graph.metadata["genre_profile_id"] == "post_apocalyptic"
    assert generation_context["resolved_profile_hash"] == graph.metadata[
        "resolved_profile_hash"
    ]
    assert result["genre_profile"]["profile"]["profile_id"] == "post_apocalyptic"
