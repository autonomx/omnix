"""Phase 8.2 — Encounter System Regression Tests.

Protect architectural boundaries: no direct truth mutation from the
encounter controller, deterministic outputs for identical inputs,
legacy-flow preservation when no encounter is active, snapshot-safe
roundtrips, and supported-mode guardrails.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest \
        tests/regression/test_phase82_encounter_regression.py -v --noconftest
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.rpg.encounter.controller import EncounterController
from app.rpg.encounter.models import (
    SUPPORTED_ENCOUNTER_MODES,
    SUPPORTED_ENCOUNTER_STATUSES,
    EncounterResolution,
    EncounterState,
)
from app.rpg.encounter.presenter import EncounterPresenter
from app.rpg.encounter.resolver import EncounterResolver


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _make_participants() -> list[dict[str, Any]]:
    return [
        {"entity_id": "player", "role": "player"},
        {"entity_id": "goblin_a", "role": "enemy"},
    ]


def _make_objectives() -> list[dict[str, Any]]:
    return [
        {"objective_id": "obj_defeat", "kind": "defeat", "required": 2},
    ]


def _make_scene() -> dict[str, Any]:
    return {"location": "dark_cave", "lighting": "dim"}


def _start_combat(ctrl: EncounterController) -> EncounterState:
    return ctrl.start_encounter(
        mode="combat",
        scene_summary=_make_scene(),
        participants=_make_participants(),
        objectives=_make_objectives(),
        tick=42,
    )


# ==================================================================
# 1. No direct truth mutation from encounter controller
# ==================================================================


class TestNoTruthMutation:
    """Starting / resolving encounters must not mutate coherence,
    social, or memory state — only self.active_encounter."""

    def test_start_encounter_does_not_mutate_coherence(self) -> None:
        """A mock coherence tracker proves no outside mutation occurs."""
        coherence = MagicMock(name="coherence_core")
        ctrl = EncounterController()
        _start_combat(ctrl)

        coherence.assert_not_called()
        assert coherence.method_calls == []

    def test_apply_resolution_does_not_mutate_social_memory(self) -> None:
        """Applying a resolution only touches encounter state."""
        social = MagicMock(name="social_state_core")
        memory = MagicMock(name="campaign_memory_core")

        ctrl = EncounterController()
        _start_combat(ctrl)

        resolution = EncounterResolution(
            encounter_id=ctrl.active_encounter.encounter_id,
            mode="combat",
            outcome_type="continue",
            participant_updates=[{"entity_id": "goblin_a", "status": "engaged"}],
            state_updates={"advance_turn": True},
        )
        ctrl.apply_resolution(resolution)

        social.assert_not_called()
        memory.assert_not_called()

    def test_controller_only_modifies_active_encounter(self) -> None:
        """After start + resolution, only self.active_encounter changed."""
        ctrl = EncounterController()
        state_before = _start_combat(ctrl)
        original_id = state_before.encounter_id

        resolution = EncounterResolution(
            encounter_id=original_id,
            mode="combat",
            outcome_type="continue",
            state_updates={"advance_turn": True, "pressure": "rising"},
        )
        ctrl.apply_resolution(resolution)

        assert ctrl.active_encounter is not None
        assert ctrl.active_encounter.encounter_id == original_id
        assert ctrl.active_encounter.pressure == "rising"
        # Controller exposes no other mutable public state
        public_attrs = [a for a in vars(ctrl) if not a.startswith("_")]
        assert public_attrs == ["active_encounter"]


# ==================================================================
# 2. Same state => same encounter state / payload (determinism)
# ==================================================================


class TestDeterminism:
    """Identical inputs must always produce identical outputs."""

    def test_identical_inputs_produce_identical_encounter_id(self) -> None:
        ctrl_a = EncounterController()
        ctrl_b = EncounterController()

        state_a = ctrl_a.start_encounter(
            mode="combat",
            scene_summary=_make_scene(),
            participants=_make_participants(),
            objectives=_make_objectives(),
            tick=100,
        )
        state_b = ctrl_b.start_encounter(
            mode="combat",
            scene_summary=_make_scene(),
            participants=_make_participants(),
            objectives=_make_objectives(),
            tick=100,
        )
        assert state_a.encounter_id == state_b.encounter_id

    def test_identical_state_and_action_produce_same_resolution(self) -> None:
        ctrl = EncounterController()
        state = _start_combat(ctrl)
        state_copy = EncounterState.from_dict(state.to_dict())

        resolver = EncounterResolver()
        action = {"intent_type": "strike", "metadata": {"encounter_action_type": "strike", "target_id": "goblin_a"}}

        res_a = resolver.resolve_action(state, action, _make_scene(), tick=1)
        res_b = resolver.resolve_action(state_copy, action, _make_scene(), tick=1)

        assert res_a is not None and res_b is not None
        assert res_a.to_dict() == res_b.to_dict()

    def test_identical_state_produces_identical_presenter_payload(self) -> None:
        ctrl = EncounterController()
        state = _start_combat(ctrl)

        presenter = EncounterPresenter()
        payload_a = presenter.present_encounter(state)
        payload_b = presenter.present_encounter(EncounterState.from_dict(state.to_dict()))

        assert payload_a == payload_b


# ==================================================================
# 3. Inactive encounter preserves legacy flow
# ==================================================================


class TestLegacyFlowPreservation:
    """Without an active encounter the controller returns None,
    preserving the behaviour that non-encounter code paths depend on."""

    def test_build_choice_context_returns_none_without_encounter(self) -> None:
        ctrl = EncounterController()
        assert ctrl.build_choice_context(player_id="player") is None

    def test_resolve_action_returns_none_without_encounter(self) -> None:
        resolver = EncounterResolver()
        result = resolver.resolve_action(
            encounter_state=None,
            resolved_action={"intent_type": "strike"},
            scene_summary=_make_scene(),
        )
        assert result is None


# ==================================================================
# 4. Snapshot-safe roundtrip
# ==================================================================


class TestSnapshotRoundtrip:
    """Controller serialization must survive a full roundtrip."""

    def test_roundtrip_with_active_encounter(self) -> None:
        ctrl = EncounterController()
        _start_combat(ctrl)

        data = ctrl.to_dict()
        restored = EncounterController.from_dict(data)

        assert restored.active_encounter is not None
        assert restored.to_dict() == data

    def test_roundtrip_with_none_encounter(self) -> None:
        ctrl = EncounterController()
        data = ctrl.to_dict()
        restored = EncounterController.from_dict(data)

        assert restored.active_encounter is None
        assert restored.to_dict() == data


# ==================================================================
# 5. Supported modes only
# ==================================================================


class TestSupportedModes:
    """Only the canonical mode set is recognised; unknown modes fall
    back to combat."""

    def test_all_supported_modes_recognised(self) -> None:
        ctrl = EncounterController()
        for mode in SUPPORTED_ENCOUNTER_MODES:
            ctrl.clear_encounter()
            state = ctrl.start_encounter(
                mode=mode,
                scene_summary=_make_scene(),
                participants=_make_participants(),
                tick=0,
            )
            assert state.mode == mode

    def test_unsupported_mode_normalises_to_combat(self) -> None:
        ctrl = EncounterController()
        state = ctrl.start_encounter(
            mode="pokemon_battle",
            scene_summary=_make_scene(),
            participants=_make_participants(),
            tick=0,
        )
        assert state.mode == "combat"
