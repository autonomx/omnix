from __future__ import annotations

import ast
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pytest

from app.apps.rpg.session import pipeline


@dataclass(frozen=True)
class _RecordingStage:
    name: str
    optional: bool
    events: list[str]

    def run(self, ctx: pipeline.TurnContext) -> pipeline.TurnContext:
        self.events.append(self.name)
        return ctx


def _context(player_input: str = "wait", action: dict[str, Any] | None = None) -> pipeline.TurnContext:
    return pipeline.TurnContext(session_id="campaign-1", player_input=player_input, action=action)


@dataclass(frozen=True)
class _ResolvingStage:
    name: str = "resolve"
    optional: bool = False

    def run(self, ctx: pipeline.TurnContext) -> pipeline.TurnContext:
        ctx.result, ctx.resolved = {"ok": True, "trace_id": ctx.trace_id}, True
        return ctx


def test_turn_pipeline_runs_stages_in_declared_order_and_resolves_once(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(pipeline, "rpg_pipeline_span", lambda *_args, **_kwargs: nullcontext({}))
    stages = (
        _RecordingStage("before", False, events),
        _ResolvingStage(),
        _RecordingStage("after", False, events),
    )

    result = pipeline.run_turn_pipeline(_context(), stages=stages)

    assert events == ["before", "after"]
    assert result.result["ok"] is True
    assert result.result["trace_id"] == result.trace_id
    assert result.resolved is True


def test_optional_turn_stage_failure_is_reported_and_pipeline_continues(monkeypatch) -> None:
    events: list[str] = []
    logged: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(pipeline, "rpg_pipeline_span", lambda *_args, **_kwargs: nullcontext({}))
    monkeypatch.setattr(
        pipeline,
        "log_rpg_event",
        lambda event, **kwargs: logged.append((event, kwargs.get("fields") or {})),
    )

    @dataclass(frozen=True)
    class _BrokenOptionalStage:
        name: str = "optional_enrichment"
        optional: bool = True

        def run(self, ctx: pipeline.TurnContext) -> pipeline.TurnContext:
            raise RuntimeError("provider unavailable")

    stages = (
        _BrokenOptionalStage(),
        _RecordingStage("after", False, events),
    )
    context = pipeline.run_turn_pipeline(_context(), stages=stages)

    assert context.degraded_stages == ["optional_enrichment"]
    assert events == ["after"]
    degraded = [row for row in logged if row[0] == "turn.stage.degraded"]
    assert degraded == [
        (
            "turn.stage.degraded",
            {
                "metric": "rpg_turn_stage_degraded",
                "stage": "optional_enrichment",
                "degraded_stage_count": 1,
            },
        )
    ]


def test_required_turn_stage_failure_propagates(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "rpg_pipeline_span", lambda *_args, **_kwargs: nullcontext({}))

    @dataclass(frozen=True)
    class _BrokenRequiredStage:
        name: str = "required_persistence"
        optional: bool = False

        def run(self, ctx: pipeline.TurnContext) -> pipeline.TurnContext:
            raise RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        pipeline.run_turn_pipeline(
            _context(),
            stages=(_BrokenRequiredStage(),),
        )


def test_production_turn_pipeline_declares_commit_and_post_commit_stages() -> None:
    stage_names = [stage.name for stage in pipeline.TURN_PIPELINE]

    assert stage_names == ["planned_turn", "interaction_commit", "interaction_lifecycle"]
    assert pipeline.TURN_PIPELINE[1].commit_boundary is True


@pytest.mark.parametrize(("player_input", "action", "error", "status"), [
    ("   ", None, "rpg_turn_empty", 400),
    ("look around", {"type": "observe"}, "rpg_turn_kind_unknown", 400),
    ("look around", None, "session_not_found", 404),
])
def test_what_the_pipeline_cannot_run_is_refused_with_no_turn(monkeypatch, player_input, action, error, status) -> None:
    """The older turn path is gone (RQ-2.10): no command falls through to another resolver."""
    from app.apps.rpg.session import session_runtime_store

    monkeypatch.setattr(session_runtime_store, "load_runtime_session", lambda _session_id: None)
    committed: list[object] = []
    monkeypatch.setattr("app.apps.rpg.session.interaction_stages.commit_interaction",
                        lambda ctx: committed.append(ctx) or ctx)

    result = pipeline.apply_turn("campaign-1", player_input, action)

    assert (result["ok"], result["error"], result["status_code"]) == (False, error, status)
    assert committed == [] or committed[0].result["ok"] is False  # the commit stage writes only a turn that ran


def test_interaction_commit_stage_updates_session_override_without_false_durability(
    monkeypatch,
) -> None:
    from app.apps.rpg.session import interaction_timeline, narrative_engine_bridge
    from app.apps.rpg.session.interaction_stages import commit_interaction

    session = {"runtime_state": {"interaction_seq": 0}}
    event = {"interaction_id": "interaction:1", "sequence": 1, "state_revision": 1}

    def commit(_session, result, **_kwargs):
        result["interaction_id"] = event["interaction_id"]
        return session, result, event

    monkeypatch.setattr(interaction_timeline, "commit_turn_interaction", commit)
    monkeypatch.setattr(
        narrative_engine_bridge,
        "canonicalize_resolved_turn_result",
        lambda result, **_kwargs: result,
    )
    context = _context()
    context.session_override = session
    context.result = {"ok": True, "session": session}

    committed = commit_interaction(context)

    assert committed.result["interaction_persisted"] is False
    assert committed.result["interaction_persistence"]["mode"] == "session_override"
    assert committed.session_override is session


def test_session_load_replays_interactions_and_recovers_pending_narration(monkeypatch) -> None:
    from app.apps.rpg.session import interaction_event_store, interaction_lifecycle, service

    session = {"manifest": {"session_id": "campaign-load"}, "runtime_state": {}}
    calls: list[str] = []

    monkeypatch.setattr(service, "load_session_from_disk", lambda _session_id: session)

    def replay(session_id, loaded):
        calls.append(f"replay:{session_id}")
        loaded["replayed"] = True
        return loaded

    def recover(session_id, loaded):
        calls.append(f"recover:{session_id}:{loaded['replayed']}")
        return 1

    monkeypatch.setattr(interaction_event_store, "load_and_replay_interaction_events", replay)
    monkeypatch.setattr(
        interaction_lifecycle,
        "recover_pending_interaction_narration",
        recover,
    )

    loaded = service.load_session("campaign-load")

    assert loaded["replayed"] is True
    assert calls == ["replay:campaign-load", "recover:campaign-load:True"]


def test_rpg_runtime_has_no_hook_installers_import_finders_or_fastapi_patchers() -> None:
    root = Path("src/app/apps/rpg")
    source_files = sorted(root.rglob("*.py"))
    installer_definitions = []
    forbidden_patches = []
    for path in source_files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        installer_definitions.extend(
            f"{path}:{node.lineno}:{node.name}"
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and re.match(r"_?install_", node.name)
        )
        if "sys.meta_path" in source or "FastAPI.__init__ =" in source:
            forbidden_patches.append(str(path))

    assert installer_definitions == []
    assert forbidden_patches == []
