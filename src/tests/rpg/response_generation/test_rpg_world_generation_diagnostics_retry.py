from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.gateway.rpg_world_library_routes import _raise_generation_error
from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.generation_diagnostics import log_world_generation_event
from app.rpg.worlds.generation_jobs import WorldTopicGenerationSettings
from app.rpg.worlds.generation_retry import retry_failed_world_generation


def test_world_generation_diagnostic_omits_prompts_and_generated_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("OMNIX_RPG_DEBUG_LOGS", "1")
    monkeypatch.setenv("OMNIX_RPG_LOG_DIR", str(tmp_path))

    payload = log_world_generation_event(
        "world_generation.job_attempt_failed",
        level="error",
        diagnostic_id="diag:test",
        world_id="world:aurelia",
        run_id="run:1",
        topic_id="classes",
        job_id="job:1",
        fields={
            "provider_route": "lmstudio",
            "model": "local-model",
            "prompt": "DO NOT WRITE THIS PROMPT",
            "generated_content": {"full_text": "DO NOT WRITE GENERATED LORE"},
            "input_payload": {"messages": ["DO NOT WRITE PROVIDER PAYLOAD"]},
            "dependency_ids": ["hero_system", "institutions"],
        },
        error=RuntimeError("x" * 3_000),
    )

    path = next(tmp_path.glob("world-generation-*.jsonl"))
    stored = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    assert payload["diagnostic_id"] == "diag:test"
    assert stored["fields"]["provider_route"] == "lmstudio"
    assert stored["fields"]["prompt"] == "[omitted]"
    assert stored["fields"]["generated_content"] == "[omitted]"
    assert stored["fields"]["input_payload"] == "[omitted]"
    assert "DO NOT WRITE" not in path.read_text(encoding="utf-8")
    assert len(stored["error"]["message"]) <= 1_200


def test_generation_internal_error_returns_diagnostic_id_and_log_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("OMNIX_RPG_DEBUG_LOGS", "1")
    monkeypatch.setenv("OMNIX_RPG_LOG_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as raised:
        _raise_generation_error(
            RuntimeError("database exploded"),
            operation="retry_failed",
            diagnostic_id="diag:500",
            run_id="run:failed",
        )

    assert raised.value.status_code == 500
    assert raised.value.detail["error"] == "world_generation_internal_error"
    assert raised.value.detail["diagnostic_id"] == "diag:500"
    assert "world-generation-" in raised.value.detail["diagnostic_log"]
    stored = json.loads(next(tmp_path.glob("world-generation-*.jsonl")).read_text(encoding="utf-8"))
    assert stored["run_id"] == "run:failed"
    assert stored["error"]["message"] == "database exploded"


def test_failed_retry_reuses_original_graph_provider_and_prompt_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = CampaignTopicGraph(
        graph_version="test",
        campaign_template="fantasy",
        depth="standard",
        nodes=(
            CampaignTopicNode("realm", "Realm", "lore"),
            CampaignTopicNode(
                "classes",
                "Classes",
                "classes",
                dependencies=("realm",),
            ),
        ),
    )
    settings = WorldTopicGenerationSettings(
        generator_version="original-generator",
        prompt_version="original-prompt",
        provider_route="lmstudio",
        model="qwen-local",
        seed=77,
        max_attempts=5,
    )
    failed_run = {
        "run_id": "run:failed",
        "world_id": "world:aurelia",
        "draft_revision": 4,
        "status": "failed",
        "graph": graph.as_dict(),
        "settings": settings.as_dict(),
        "progress": {"failed_topic_ids": ["classes"]},
        "context": {
            "generation_context": {
                "genre": "fantasy",
                "tone": "dark academia",
                "starting_location": "location:hall",
                "background_expansion": True,
            },
            "topic_directives": {"classes": {"direction": "Keep class names concise"}},
            "entity_manifest_hash": "sha256:manifest",
        },
    }

    class FakeWork:
        world_generation = SimpleNamespace(get=lambda context, run_id: failed_run)
        world_library = SimpleNamespace(
            list_topics=lambda context, world_id: [
                {"topic_id": "realm", "status": "ready", "provenance": {}},
            ]
        )

        def rollback(self) -> None:
            return None

    class FakeUnitOfWork:
        def __enter__(self):
            return FakeWork()

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    captured: dict[str, object] = {}
    worker_call: dict[str, object] = {}

    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.bootstrap_local_tenant",
        lambda database=None: SimpleNamespace(workspace_id="workspace:test"),
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.unit_of_work",
        lambda database=None: FakeUnitOfWork(),
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.require_world_writable",
        lambda work, context, world_id: {"id": world_id, "draft_revision": 4},
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry._graph_from_payload",
        lambda payload: graph,
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry._settings_from_payload",
        lambda payload: settings,
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.resolve_generation_scope",
        lambda *args, **kwargs: (
            ("realm", "classes"),
            ("classes",),
            {
                "mode": "failed",
                "topic_ids": ["classes"],
                "resolved_topic_ids": ["realm", "classes"],
            },
        ),
    )

    def start_world_generation(**kwargs):
        captured.update(kwargs)
        return {"run_id": "run:retry", "status": "running"}

    def kick_world_generation_worker(**kwargs):
        worker_call.update(kwargs)
        return True

    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.start_world_generation",
        start_world_generation,
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.kick_world_generation_worker",
        kick_world_generation_worker,
    )
    monkeypatch.setattr(
        "app.rpg.worlds.generation_retry.log_world_generation_event",
        lambda *args, **kwargs: {},
    )

    result = retry_failed_world_generation(
        "run:failed",
        kick_worker=True,
        diagnostic_id="diag:retry",
    )

    assert result["run"]["run_id"] == "run:retry"
    assert result["retry_of_run_id"] == "run:failed"
    assert captured["graph"] is graph
    assert captured["settings"] is settings
    assert captured["generation_context"] == failed_run["context"]["generation_context"]
    assert captured["topic_directives"] == failed_run["context"]["topic_directives"]
    assert captured["entity_manifest_hash"] == "sha256:manifest"
    assert captured["target_topic_ids"] == ("realm", "classes")
    assert captured["forced_topic_ids"] == ("classes",)
    assert captured["strategy"] == "force"
    assert captured["scope"]["retry_of_run_id"] == "run:failed"
    assert worker_call["provider_route"] == "lmstudio"
