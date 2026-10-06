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


def _context(execute_core: Any) -> pipeline.TurnContext:
    return pipeline.TurnContext(
        session_id="campaign-1",
        player_input="wait",
        action=None,
        performance_override=None,
        session_override=None,
        execute_core=execute_core,
    )


def test_turn_pipeline_runs_stages_in_declared_order_and_resolves_once(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(pipeline, "rpg_pipeline_span", lambda *_args, **_kwargs: nullcontext({}))
    context = _context(lambda: events.append("core") or {"ok": True})
    stages = (
        _RecordingStage("before", False, events),
        pipeline.CoreResolutionStage(),
        _RecordingStage("after", False, events),
    )

    result = pipeline.run_turn_pipeline(context, stages=stages)

    assert events == ["before", "core", "after"]
    assert result.result["ok"] is True
    assert result.result["trace_id"] == result.trace_id
    assert result.resolved is True


def test_public_interactive_turn_routes_through_the_pipeline_core(monkeypatch) -> None:
    from app.apps.rpg.session import interactive_first_call_runtime

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        interactive_first_call_runtime,
        "_apply_turn_core",
        lambda session_id, player_input, action, **_kwargs: calls.append(
            (session_id, player_input)
        )
        or {"ok": False, "error": "focused_test"},
    )

    result = interactive_first_call_runtime.apply_turn(
        "campaign-2",
        "wait",
        performance_override={"fast_visible_dialogue": False},
    )

    assert result["error"] == "focused_test"
    assert calls == [("campaign-2", "wait")]


def test_fast_visible_dialogue_stage_short_circuits_stateful_resolution(monkeypatch) -> None:
    from app.apps.rpg.session import fast_visible_dialogue_hook

    monkeypatch.setattr(
        pipeline,
        "rpg_pipeline_span",
        lambda *_args, **_kwargs: nullcontext({}),
    )
    monkeypatch.setattr(
        fast_visible_dialogue_hook,
        "try_fast_visible_dialogue",
        lambda _ctx: {"ok": True, "fast_visible_dialogue": True},
    )
    core_calls: list[bool] = []
    context = _context(lambda: core_calls.append(True) or {"ok": True})

    result = pipeline.run_turn_pipeline(
        context,
        stages=(pipeline.FastVisibleDialogueStage(), pipeline.CoreResolutionStage()),
    )

    assert result.result == {"ok": True, "fast_visible_dialogue": True}
    assert core_calls == []


def test_dialogue_quality_stage_enforces_resolved_visible_result(monkeypatch) -> None:
    from app.apps.rpg.session import dialogue_quality_hook

    monkeypatch.setattr(
        dialogue_quality_hook,
        "enforce_dialogue_quality",
        lambda result, **_kwargs: {**result, "quality_checked": True},
    )
    context = _context(lambda: None)
    context.result = {"ok": True, "session": {"simulation_state": {}}}

    result = pipeline.DialogueQualityStage().run(context)

    assert result.result["quality_checked"] is True
    assert result.result["dialogue_quality_hook_applied"] is True


def test_semantic_action_prompt_owns_the_dialogue_quality_contract() -> None:
    from app.apps.rpg.ai.semantic_action_intelligence import build_semantic_action_prompt

    prompt = build_semantic_action_prompt("ask about the road", {}, {}, {})

    assert "DIALOGUE_QUALITY_CONTRACT:" in prompt
    assert "Aim for 45-110 words total" in prompt


def test_visible_response_stage_attaches_canonical_turn_record() -> None:
    from app.apps.rpg.session.visible_response_stage import apply_visible_response_stage

    context = _context(lambda: None)
    context.result = {
        "ok": True,
        "visible_response": {
            "narration": "The rain taps against the inn windows.",
            "npc": {"speaker": "Mara", "line": "The eastern road is quiet."},
        },
    }

    result = apply_visible_response_stage(context)

    assert result.result["visible_turn_record"]["visible_text_valid"] is True
    assert result.result["visible_turn_record"]["player_input"] == "wait"


def test_provider_visible_text_falls_back_to_assistant_message_content() -> None:
    from app.apps.rpg.ai.semantic_action_intelligence import _complete_raw_text

    class Provider:
        def complete_semantic_packet(self, _prompt: str, *, response_schema: dict[str, Any]) -> dict[str, Any]:
            assert response_schema["type"] == "object"
            return {
                "text": "tool_calls: []",
                "choices": [{"message": {"content": "Mara points toward the eastern road."}}],
            }

    _result, raw_text, source = _complete_raw_text(Provider(), "prompt")

    assert raw_text == "Mara points toward the eastern road."
    assert source.endswith(":choices_message_content")


def test_first_call_selection_rejects_placeholder_and_world_info_text() -> None:
    from app.apps.rpg.session.visible_response_contract import validate_first_call_selection

    placeholder = validate_first_call_selection(
        {
            "consumable": True,
            "source": "semantic_advisory",
            "visible_response": {"npc": {"line": "[NPC line will be filled later]"}},
        }
    )
    world_info = validate_first_call_selection(
        {
            "consumable": True,
            "source": "semantic_advisory",
            "visible_response": {
                "narration": "Mara pauses beside the map.",
                "npc": {"speaker": "Mara", "line": "The mill road has been quiet."},
            },
            "first_call_grounding_diagnostics": {
                "turn_grounding_packet": {
                    "player_input": "Any news about the mill?",
                    "priority_context": {"addressed_npc_ids": ["mara"]},
                    "npc_context": {"addressed_npcs": [{"id": "mara", "name": "Mara"}]},
                }
            },
        }
    )

    assert placeholder["consumable"] is False
    assert placeholder["source"] == "first_call_dialogue_placeholder_guard_v1"
    assert world_info["rejection_reasons"] == [
        "semantic_advisory:world_info_inquiry_requires_runtime"
    ]


def test_generic_dialogue_fallback_repairs_meaningful_question_and_preserves_noise() -> None:
    from app.apps.rpg.session.interactive_first_call_runtime import _safe_dialogue_fallback_line

    repaired = _safe_dialogue_fallback_line(
        speaker="Mara",
        profile={"role": "road warden"},
        player_input="What is the first thing you notice?",
    )
    noise = _safe_dialogue_fallback_line(
        speaker="Mara",
        profile={"role": "road warden"},
        player_input="[object Object]",
    )

    assert repaired[0] == "information_inquiry"
    assert "considers the question" in repaired[1]
    assert noise == (
        "general_dialogue",
        "Ask that plainly again, and I will answer as best I can.",
    )


def test_direct_dialogue_owner_records_conversation_exchange(monkeypatch) -> None:
    from app.apps.rpg.session import canonical_direct_dialogue, dialogue_focus, first_call_dialogue

    monkeypatch.setattr(
        first_call_dialogue,
        "choose_first_call_visible_response",
        lambda **_kwargs: {"consumable": True, "source": "focused_test"},
    )
    monkeypatch.setattr(
        canonical_direct_dialogue,
        "build_canonical_direct_dialogue_intent",
        lambda **_kwargs: {"turn_id": "turn-12"},
    )
    # canonicalize_direct_dialogue_result is imported from narrative_engine_bridge.
    from app.apps.rpg.session import narrative_engine_bridge

    monkeypatch.setattr(
        narrative_engine_bridge,
        "canonicalize_direct_dialogue_result",
        lambda *_args, **_kwargs: {"consumed": True, "ok": True, "turn_id": "turn-12"},
    )
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        dialogue_focus,
        "record_direct_dialogue_exchange",
        lambda **kwargs: recorded.append(kwargs) or {"recorded": True},
    )

    result = first_call_dialogue.build_non_stateful_dialogue_result(
        session={"manifest": {"session_id": "campaign-12"}},
        simulation_state={},
        runtime_state={"tick": 12},
        player_input="Any news from the road?",
    )

    assert result["ok"] is True
    assert len(recorded) == 1
    assert recorded[0]["turn_id"] == "turn-12"
    assert recorded[0]["persist"] is True


def test_direct_dialogue_recording_failure_emits_degradation_metric(monkeypatch) -> None:
    from app.apps.rpg.session import canonical_direct_dialogue, dialogue_focus, first_call_dialogue
    from app.apps.rpg.session import narrative_engine_bridge

    monkeypatch.setattr(
        first_call_dialogue,
        "choose_first_call_visible_response",
        lambda **_kwargs: {"consumable": True, "source": "focused_test"},
    )
    monkeypatch.setattr(
        canonical_direct_dialogue,
        "build_canonical_direct_dialogue_intent",
        lambda **_kwargs: {"turn_id": "turn-13"},
    )
    monkeypatch.setattr(
        narrative_engine_bridge,
        "canonicalize_direct_dialogue_result",
        lambda *_args, **_kwargs: {"consumed": True, "ok": True, "turn_id": "turn-13"},
    )

    def fail_recording(**_kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(dialogue_focus, "record_direct_dialogue_exchange", fail_recording)
    logged: list[dict[str, Any]] = []
    from app.apps.rpg import debug_logging

    monkeypatch.setattr(
        debug_logging,
        "log_rpg_event",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}) or {},
    )

    result = first_call_dialogue.build_non_stateful_dialogue_result(
        session={"manifest": {"session_id": "campaign-13"}},
        simulation_state={},
        runtime_state={"tick": 13},
        player_input="Any news from the road?",
    )

    assert result["conversation_thread_record"]["recorded"] is False
    assert logged[0]["event"] == "turn.stage.degraded"
    assert logged[0]["fields"]["metric"] == "rpg_turn_stage_degraded"
    assert logged[0]["fields"]["stage"] == "direct_dialogue_focus"


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
    context = pipeline.run_turn_pipeline(_context(lambda: {"ok": True}), stages=stages)

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
            _context(lambda: {"ok": True}),
            stages=(_BrokenRequiredStage(),),
        )


def test_production_turn_pipeline_declares_commit_and_post_commit_stages() -> None:
    stage_names = [stage.name for stage in pipeline.TURN_PIPELINE]

    assert stage_names == [
        "fast_visible_dialogue",
        "resolve",
        "fast_combat_result",
        "dialogue_quality",
        "visible_response",
        "player_agency",
        "interaction_commit",
        "interaction_lifecycle",
    ]
    assert pipeline.TURN_PIPELINE[6].commit_boundary is True


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
    context = _context(lambda: None)
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


@pytest.mark.parametrize(
    ("player_input", "expected_intent", "expected_family"),
    [
        ("I used to ride with dragons", "lore_conflict_claim", "claim"),
        ("What if I became a king?", "hypothetical_counterfactual", "hypothetical"),
    ],
)
def test_interpretive_owner_builds_world_contracts_without_installers(
    player_input: str,
    expected_intent: str,
    expected_family: str,
) -> None:
    from app.apps.rpg.session.interpretive_adjudication import (
        build_interpretive_adjudication_result,
    )

    result = build_interpretive_adjudication_result(
        session={"manifest": {"session_id": "campaign-interpretive"}},
        simulation_state={"currency": {"gold": 3}, "inventory": []},
        runtime_state={"tick": 4},
        player_input=player_input,
        semantic_advisory={
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:mara",
            "target_name": "Mara",
        },
        selection={"consumable": False, "reason": "no_safe_non_stateful_visible_response"},
    )

    resolved = result["resolved_result"]
    assert resolved["interpretive_intent"] == expected_intent
    assert result["world_assessment"]["verification"] in {
        "unverified",
        "counterfactual",
    }
    assert resolved["interpretive_intent_family"] == expected_family
    assert result["intent_result"]
    assert result["turn_plan"]
    assert result["reasoning_trace"]


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
