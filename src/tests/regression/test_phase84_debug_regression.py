"""Phase 8.4 — Deterministic Debug ID Regression Tests.

These tests verify that debug trace IDs and GM bundle IDs are fully
deterministic — derived from stable inputs (tick, choice_id, etc.)
and never from uuid4() or other random sources.
"""

import pytest


class TestPhase84DeterministicDebugIds:
    """Regression tests for Phase 8.4 deterministic debug ID hardening."""

    def test_choice_trace_ids_are_deterministic(self):
        """Choice trace IDs must be identical for the same inputs."""
        from app.rpg.debug.trace_builder import DebugTraceBuilder

        builder = DebugTraceBuilder()
        control_output = {
            "choice_set": {
                "options": [
                    {"option_id": "opt_b", "label": "Second"},
                    {"option_id": "opt_a", "label": "First"},
                ]
            }
        }
        trace1 = builder.build_choice_trace(control_output, tick=7).to_dict()
        trace2 = builder.build_choice_trace(control_output, tick=7).to_dict()

        assert trace1["trace_id"] == trace2["trace_id"], (
            "trace_id must be deterministic for same inputs"
        )
        assert [n["node_id"] for n in trace1["nodes"]] == [
            n["node_id"] for n in trace2["nodes"]
        ], "node_ids must be deterministic and in same order"

    def test_choice_trace_ids_differ_by_tick(self):
        """Choice trace IDs must differ when tick differs."""
        from app.rpg.debug.trace_builder import DebugTraceBuilder

        builder = DebugTraceBuilder()
        control_output = {
            "choice_set": {
                "options": [
                    {"option_id": "opt_a", "label": "First"},
                ]
            }
        }
        trace1 = builder.build_choice_trace(control_output, tick=7).to_dict()
        trace2 = builder.build_choice_trace(control_output, tick=8).to_dict()

        assert trace1["trace_id"] != trace2["trace_id"], (
            "trace_id must differ when tick changes"
        )

    def test_action_trace_ids_are_deterministic(self):
        """Action trace IDs must be identical for the same inputs."""
        from app.rpg.debug.trace_builder import DebugTraceBuilder

        builder = DebugTraceBuilder()
        action_result = {
            "resolved_action": {
                "option_id": "choice_attack",
                "action_id": "act_001",
                "intent_type": "attack",
                "metadata": {},
            },
            "events": [],
            "trace": {},
        }
        trace1 = builder.build_action_trace(action_result, tick=12).to_dict()
        trace2 = builder.build_action_trace(action_result, tick=12).to_dict()

        assert trace1["trace_id"] == trace2["trace_id"], (
            "action trace_id must be deterministic for same inputs"
        )
        assert [n["node_id"] for n in trace1["nodes"]] == [
            n["node_id"] for n in trace2["nodes"]
        ], "action node_ids must be deterministic and in same order"

    def test_gm_bundle_id_is_deterministic(self):
        """GM bundle_id must be identical for the same inputs."""
        from app.rpg.debug.core import DebugCore

        core = DebugCore()
        kwargs = {
            "tick": 9,
            "scene_payload": {"scene": {"location": "dock"}},
            "action_result": {"choice_id": "choice_negotiate"},
            "control_output": {"choice_set": {"options": []}},
            "last_dialogue_response": {},
            "last_dialogue_trace": {},
            "last_encounter_resolution": {},
            "last_encounter_state": {},
            "last_world_sim_result": {},
            "last_world_sim_state": {},
            "arc_debug_summary": {},
            "recovery_debug_summary": {},
            "pack_debug_summary": {},
        }
        bundle1 = core.build_gm_inspection_bundle(**kwargs)
        bundle2 = core.build_gm_inspection_bundle(**kwargs)

        assert "bundle_id" in bundle1.get("metadata", {}), (
            "bundle must contain bundle_id in metadata"
        )
        assert bundle1["metadata"]["bundle_id"] == bundle2["metadata"]["bundle_id"], (
            "bundle_id must be deterministic for same inputs"
        )

    def test_debug_payload_is_fully_stable_for_same_inputs(self):
        """Full GM inspection bundle must be identical across replays."""
        from app.rpg.debug.core import DebugCore

        core = DebugCore()
        kwargs = {
            "tick": 4,
            "scene_payload": {"scene": {"location": "square"}},
            "action_result": {"choice_id": "choice_wait"},
            "control_output": {
                "choice_set": {
                    "options": [
                        {"option_id": "wait", "label": "Wait"}
                    ]
                }
            },
            "last_dialogue_response": {"act": "acknowledge"},
            "last_dialogue_trace": {"reasons": ["neutral interaction"]},
            "last_encounter_resolution": {},
            "last_encounter_state": {},
            "last_world_sim_result": {
                "tick": 4,
                "generated_effects": [],
            },
            "last_world_sim_state": {},
            "arc_debug_summary": {},
            "recovery_debug_summary": {},
            "pack_debug_summary": {},
        }
        bundle1 = core.build_gm_inspection_bundle(**kwargs)
        bundle2 = core.build_gm_inspection_bundle(**kwargs)

        assert bundle1 == bundle2, (
            "Full GM inspection bundle must be identical for same inputs"
        )

    def test_trace_id_format_is_stable_prefix(self):
        """Trace IDs should use a stable prefix format."""
        from app.rpg.debug.trace_builder import DebugTraceBuilder

        builder = DebugTraceBuilder()
        control_output = {
            "choice_set": {
                "options": [
                    {"option_id": "opt_a", "label": "Test"},
                ]
            }
        }
        trace = builder.build_choice_trace(control_output, tick=5).to_dict()
        trace_id = trace["trace_id"]

        assert trace_id.startswith("debug-trace:"), (
            f"trace_id should start with 'debug-trace:', got: {trace_id}"
        )

    def test_node_id_format_is_stable_prefix(self):
        """Node IDs should use a stable prefix format."""
        from app.rpg.debug.trace_builder import DebugTraceBuilder

        builder = DebugTraceBuilder()
        control_output = {
            "choice_set": {
                "options": [
                    {"option_id": "opt_a", "label": "Test"},
                ]
            }
        }
        trace = builder.build_choice_trace(control_output, tick=5).to_dict()

        for node in trace["nodes"]:
            node_id = node["node_id"]
            assert node_id.startswith("debug-node:"), (
                f"node_id should start with 'debug-node:', got: {node_id}"
            )