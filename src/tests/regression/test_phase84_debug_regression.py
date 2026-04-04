"""Phase 8.4 — Debug / Analytics / GM Inspection — Regression Tests.

Ensures:
- Same inputs always produce structurally identical debug payloads.
- Debug builds never mutate source system data.
- Missing/empty source data yields 'unavailable' markers, never fabricated reasons.
- Large inputs produce bounded output sections.
- All node types and scopes belong to the declared supported sets.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/regression/test_phase84_debug_regression.py -v --noconftest
"""

import copy

import pytest

from app.rpg.debug.core import DebugCore
from app.rpg.debug.trace_builder import DebugTraceBuilder
from app.rpg.debug.presenter import DebugPresenter
from app.rpg.debug.models import (
    DebugTrace,
    DebugTraceNode,
    ChoiceExplanation,
    NPCResponseExplanation,
    EncounterExplanation,
    WorldSimExplanation,
    GMInspectionBundle,
    SUPPORTED_DEBUG_NODE_TYPES,
    SUPPORTED_DEBUG_SCOPES,
)


# ------------------------------------------------------------------
# Shared fixtures / helpers
# ------------------------------------------------------------------

_CONTROL_OUTPUT: dict = {
    "choice_set": {
        "options": [
            {
                "option_id": "opt1",
                "label": "Attack",
                "intent_type": "combat",
                "summary": "Attack the enemy",
                "priority": 1.0,
                "tags": ["combat"],
                "metadata": {"debug_source": "standard"},
                "constraints": [],
            },
        ],
    },
    "pacing": {"tempo": "normal"},
    "framing": {},
}

_ACTION_RESULT: dict = {
    "resolved_action": {
        "action_id": "act1",
        "option_id": "opt1",
        "intent_type": "combat",
        "summary": "Attack",
        "outcome": "success",
        "metadata": {
            "mapped_action": {"intent_type": "combat"},
            "evaluation": {"outcome": "success"},
        },
    },
    "events": [{"event_type": "combat_hit", "payload": {}}],
    "trace": {},
}

_DIALOGUE_RESPONSE: dict = {
    "speaker_id": "npc_guard",
    "listener_id": "player",
    "act": "warn",
    "tone": "stern",
    "stance": "hostile",
    "summary": "Guard warns you.",
}

_DIALOGUE_TRACE: dict = {
    "decision_reasons": ["Player trespassed"],
    "state_drivers": {"loyalty": "low"},
    "primary_act": "warn",
}

_ENCOUNTER_STATE: dict = {
    "encounter_id": "enc1",
    "mode": "combat",
    "status": "active",
    "pressure": 0.7,
    "stakes": "high",
    "round_index": 2,
}

_ENCOUNTER_TRACE: dict = {
    "mode": "combat",
    "outcome_type": "ongoing",
    "reasons": ["Enemy engaged"],
    "participant_updates": [{"id": "npc1", "hp_delta": -5}],
    "objective_updates": [],
}

_WORLD_RESULT: dict = {
    "tick": 10,
    "generated_effects": [
        {"effect_type": "thread_pressure_changed", "scope": "global", "target_id": "t1"},
        {"effect_type": "rumor_spread", "scope": "local", "target_id": "r1"},
    ],
    "advanced": True,
}

_WORLD_STATE: dict = {"time_of_day": "dusk"}


@pytest.fixture
def core() -> DebugCore:
    return DebugCore()


@pytest.fixture
def builder() -> DebugTraceBuilder:
    return DebugTraceBuilder()


def _strip_uuids(d: dict) -> dict:
    """Recursively replace UUID-bearing string values with a placeholder.

    trace_id and node_id fields contain generated UUIDs that differ
    across invocations.  For structural comparison we replace them.
    """
    out: dict = {}
    for k, v in d.items():
        if k in ("trace_id", "node_id"):
            out[k] = "__UUID__"
        elif isinstance(v, dict):
            out[k] = _strip_uuids(v)
        elif isinstance(v, list):
            out[k] = [
                _strip_uuids(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            out[k] = v
    return out


# ==================================================================
# 1. Same inputs → same debug payload (determinism)
# ==================================================================


class TestDeterminism:
    """Identical inputs must produce structurally identical outputs."""

    def test_choice_debug_payload_determinism(self, core: DebugCore) -> None:
        a = core.build_choice_debug_payload(copy.deepcopy(_CONTROL_OUTPUT), tick=1)
        b = core.build_choice_debug_payload(copy.deepcopy(_CONTROL_OUTPUT), tick=1)
        assert _strip_uuids(a) == _strip_uuids(b)

    def test_action_debug_payload_determinism(self, core: DebugCore) -> None:
        a = core.build_action_debug_payload(copy.deepcopy(_ACTION_RESULT), tick=1)
        b = core.build_action_debug_payload(copy.deepcopy(_ACTION_RESULT), tick=1)
        assert _strip_uuids(a) == _strip_uuids(b)

    def test_gm_inspection_bundle_determinism(self, core: DebugCore) -> None:
        kwargs = dict(
            tick=5,
            control_output=copy.deepcopy(_CONTROL_OUTPUT),
            action_result=copy.deepcopy(_ACTION_RESULT),
            last_dialogue_response=copy.deepcopy(_DIALOGUE_RESPONSE),
            last_dialogue_trace=copy.deepcopy(_DIALOGUE_TRACE),
            last_encounter_state=copy.deepcopy(_ENCOUNTER_STATE),
            last_encounter_resolution=copy.deepcopy(_ENCOUNTER_TRACE),
            last_world_sim_result=copy.deepcopy(_WORLD_RESULT),
            last_world_sim_state=copy.deepcopy(_WORLD_STATE),
        )
        a = core.build_gm_inspection_bundle(**kwargs)
        b = core.build_gm_inspection_bundle(**kwargs)

        sa, sb = _strip_uuids(a), _strip_uuids(b)
        assert sa.keys() == sb.keys()
        assert sa == sb

    def test_system_debug_snapshot_determinism(self, core: DebugCore) -> None:
        kwargs = dict(
            tick=5,
            control_output=copy.deepcopy(_CONTROL_OUTPUT),
            action_result=copy.deepcopy(_ACTION_RESULT),
            last_dialogue_response=copy.deepcopy(_DIALOGUE_RESPONSE),
            has_encounter=True,
            world_effect_count=3,
            warning_count=1,
            arc_summary={"active_arcs": ["a1"]},
        )
        a = core.build_system_debug_snapshot(**kwargs)
        b = core.build_system_debug_snapshot(**kwargs)
        # No UUIDs in system snapshot — exact equality expected.
        assert a == b


# ==================================================================
# 2. Debug build does not mutate source systems
# ==================================================================


class TestNoMutation:
    """Building debug payloads must never mutate the original inputs."""

    def test_control_output_not_mutated(self, core: DebugCore) -> None:
        original = copy.deepcopy(_CONTROL_OUTPUT)
        frozen = copy.deepcopy(original)
        core.build_choice_debug_payload(original, tick=1)
        assert original == frozen

    def test_action_result_not_mutated(self, core: DebugCore) -> None:
        original = copy.deepcopy(_ACTION_RESULT)
        frozen = copy.deepcopy(original)
        core.build_action_debug_payload(original, tick=1)
        assert original == frozen

    def test_dialogue_inputs_not_mutated(self, builder: DebugTraceBuilder) -> None:
        resp = copy.deepcopy(_DIALOGUE_RESPONSE)
        trace = copy.deepcopy(_DIALOGUE_TRACE)
        frozen_resp = copy.deepcopy(resp)
        frozen_trace = copy.deepcopy(trace)
        builder.build_dialogue_explanation(resp, trace)
        assert resp == frozen_resp
        assert trace == frozen_trace

    def test_gm_bundle_inputs_not_mutated(self, core: DebugCore) -> None:
        co = copy.deepcopy(_CONTROL_OUTPUT)
        ar = copy.deepcopy(_ACTION_RESULT)
        dr = copy.deepcopy(_DIALOGUE_RESPONSE)
        dt = copy.deepcopy(_DIALOGUE_TRACE)
        es = copy.deepcopy(_ENCOUNTER_STATE)
        et = copy.deepcopy(_ENCOUNTER_TRACE)
        wr = copy.deepcopy(_WORLD_RESULT)
        ws = copy.deepcopy(_WORLD_STATE)

        frozen = {
            "co": copy.deepcopy(co),
            "ar": copy.deepcopy(ar),
            "dr": copy.deepcopy(dr),
            "dt": copy.deepcopy(dt),
            "es": copy.deepcopy(es),
            "et": copy.deepcopy(et),
            "wr": copy.deepcopy(wr),
            "ws": copy.deepcopy(ws),
        }

        core.build_gm_inspection_bundle(
            tick=1,
            control_output=co,
            action_result=ar,
            last_dialogue_response=dr,
            last_dialogue_trace=dt,
            last_encounter_state=es,
            last_encounter_resolution=et,
            last_world_sim_result=wr,
            last_world_sim_state=ws,
        )

        assert co == frozen["co"]
        assert ar == frozen["ar"]
        assert dr == frozen["dr"]
        assert dt == frozen["dt"]
        assert es == frozen["es"]
        assert et == frozen["et"]
        assert wr == frozen["wr"]
        assert ws == frozen["ws"]


# ==================================================================
# 3. No invented reasons
# ==================================================================


class TestNoInventedReasons:
    """When source data is absent/empty the debug layer must indicate
    unavailability rather than fabricate detailed explanations."""

    def test_dialogue_empty_trace_yields_unavailable_or_act(
        self, builder: DebugTraceBuilder,
    ) -> None:
        resp = {"speaker_id": "npc1", "act": "greet"}
        expl = builder.build_dialogue_explanation(resp, {})
        # With an empty trace the builder should fall back to the act
        # field or report "unavailable" — never a fabricated driver.
        for reason in expl.reasons:
            r_lower = reason.lower()
            assert (
                "unavailable" in r_lower
                or "act" in r_lower
            ), f"Unexpected fabricated reason: {reason!r}"

    def test_encounter_empty_state_yields_unavailable(
        self, builder: DebugTraceBuilder,
    ) -> None:
        expl = builder.build_encounter_explanation({}, None)
        assert any("unavailable" in r.lower() for r in expl.reasons), (
            f"Expected 'unavailable' marker, got: {expl.reasons}"
        )

    def test_world_sim_empty_result_yields_did_not_advance(
        self, builder: DebugTraceBuilder,
    ) -> None:
        result = {"generated_effects": [], "advanced": False}
        expl = builder.build_world_sim_explanation(result)
        joined = " ".join(expl.reasons).lower()
        assert "did not advance" in joined, (
            f"Expected 'did not advance' marker, got: {expl.reasons}"
        )

    def test_gm_bundle_all_none_no_fabricated_reason_lists(
        self, core: DebugCore,
    ) -> None:
        bundle = core.build_gm_inspection_bundle(tick=0)
        # With all-None inputs every reason list must be empty.
        for section_key in (
            "dialogue_summary",
            "encounter_summary",
            "world_summary",
        ):
            section = bundle.get(section_key, {})
            reasons = section.get("reasons", [])
            assert reasons == [] or all(
                "unavailable" in r.lower()
                or "did not" in r.lower()
                or "act" in r.lower()
                for r in reasons
            ), f"Fabricated reasons in {section_key}: {reasons}"


# ==================================================================
# 4. Bounded payload size / sections
# ==================================================================


class TestBoundedPayload:
    """Large inputs must still yield bounded output."""

    def test_choice_trace_with_100_options(self, builder: DebugTraceBuilder) -> None:
        options = [
            {
                "option_id": f"opt{i}",
                "label": f"Option {i}",
                "intent_type": "explore",
                "summary": f"Do thing {i}",
                "priority": float(i),
                "tags": [],
                "metadata": {},
                "constraints": [],
            }
            for i in range(100)
        ]
        control = {"choice_set": {"options": options}, "pacing": {}, "framing": {}}
        trace = builder.build_choice_trace(control, tick=1)

        # Every option should generate a node (plus possible context node).
        assert len(trace.nodes) >= 100
        # Each node's reason list must be bounded by _MAX_REASONS (20).
        for node in trace.nodes:
            assert len(node.reasons) <= 20

    def test_world_sim_200_effects_bounded(
        self, builder: DebugTraceBuilder,
    ) -> None:
        effects = [
            {"effect_type": f"type_{i % 5}", "scope": "global", "target_id": f"t{i}"}
            for i in range(200)
        ]
        result = {"generated_effects": effects, "advanced": True, "tick": 1}
        expl = builder.build_world_sim_explanation(result)
        # _MAX_EFFECTS = 50
        assert len(expl.effects) <= 50

    def test_gm_bundle_large_data_bounded(self, core: DebugCore) -> None:
        options = [
            {
                "option_id": f"opt{i}",
                "label": f"Opt {i}",
                "intent_type": "misc",
                "summary": "",
                "priority": 0.5,
                "tags": [],
                "metadata": {},
                "constraints": [],
            }
            for i in range(60)
        ]
        effects = [
            {"effect_type": "tick", "scope": "global", "target_id": f"e{i}"}
            for i in range(200)
        ]
        bundle = core.build_gm_inspection_bundle(
            tick=1,
            control_output={"choice_set": {"options": options}, "pacing": {}, "framing": {}},
            last_world_sim_result={"generated_effects": effects, "advanced": True, "tick": 1},
        )

        assert isinstance(bundle, dict)
        # Presenter bounds choices to _MAX_CHOICES_IN_SUMMARY (20).
        assert len(bundle.get("choices", [])) <= 20
        # Warnings bounded to _MAX_WARNINGS_IN_SUMMARY (15).
        assert len(bundle.get("warnings", [])) <= 15
        # World effects bounded at builder level (50).
        world = bundle.get("world_summary", {})
        assert world.get("effect_count", 0) <= 50


# ==================================================================
# 5. Supported node types / scopes only
# ==================================================================


class TestSupportedTypesAndScopes:
    """Every produced node type and scope must belong to the declared
    supported sets."""

    def test_choice_trace_node_types(self, builder: DebugTraceBuilder) -> None:
        trace = builder.build_choice_trace(_CONTROL_OUTPUT, tick=1)
        for node in trace.nodes:
            assert node.node_type in SUPPORTED_DEBUG_NODE_TYPES, (
                f"Unsupported node_type: {node.node_type!r}"
            )

    def test_action_trace_node_types(self, builder: DebugTraceBuilder) -> None:
        trace = builder.build_action_trace(_ACTION_RESULT, tick=1)
        for node in trace.nodes:
            assert node.node_type in SUPPORTED_DEBUG_NODE_TYPES, (
                f"Unsupported node_type: {node.node_type!r}"
            )

    def test_trace_scopes_supported(self, builder: DebugTraceBuilder) -> None:
        choice_trace = builder.build_choice_trace(_CONTROL_OUTPUT, tick=1)
        assert choice_trace.scope in SUPPORTED_DEBUG_SCOPES, (
            f"Unsupported choice scope: {choice_trace.scope!r}"
        )
        action_trace = builder.build_action_trace(_ACTION_RESULT, tick=1)
        assert action_trace.scope in SUPPORTED_DEBUG_SCOPES, (
            f"Unsupported action scope: {action_trace.scope!r}"
        )
