"""Phase 15 — Tactical Mode Fix Regression Tests.

Tests for encounter state normalization, action log bounding,
and deterministic validation.
"""

from app.rpg.encounter.tactical_mode import (
    MAX_ACTION_LOG,
    MAX_ROUNDS,
    ActionResolver,
    EncounterDeterminismValidator,
    EncounterTacticalState,
    TacticalAction,
    TacticalParticipant,
)


class TestPhase15TacticalModeFixRegression:
    """Regression tests for Phase 15 tactical mode fixes."""

    def test_phase15_normalize_state_rebuilds_turn_order_and_clamps_turn_index(self):
        """Verify normalize_state rebuilds turn_order and clamps turn_index."""
        state = EncounterTacticalState(
            encounter_id="enc:1",
            mode="invalid",
            status="invalid",
            round_number=999,
            turn_index=99,
            participants=[
                TacticalParticipant(entity_id="b", name="B", initiative=1.0, status="active"),
                TacticalParticipant(entity_id="a", name="A", initiative=2.0, status="active"),
            ],
            turn_order=["missing"],
            action_log=[],
            active_effects=[],
        )
        out = EncounterDeterminismValidator.normalize_state(state)
        assert out.mode == "combat"
        assert out.status == "inactive"
        assert out.round_number == MAX_ROUNDS
        assert out.turn_order == ["a", "b"]
        assert out.turn_index == 1

    def test_phase15_action_log_is_bounded(self):
        """Verify action_log is bounded to MAX_ACTION_LOG."""
        state = EncounterTacticalState(
            participants=[
                TacticalParticipant(entity_id="a", name="A", initiative=1.0, status="active"),
                TacticalParticipant(entity_id="b", name="B", initiative=1.0, status="active"),
            ]
        )
        for i in range(250):
            ActionResolver.resolve_action(
                TacticalAction(action_id=str(i), actor_id="a", action_type="attack", target_id="b", value=1.0),
                state,
            )
        out = EncounterDeterminismValidator.normalize_state(state)
        assert len(out.action_log) == MAX_ACTION_LOG

    def test_phase15_validate_bounds_catches_invalid_mode(self):
        """Verify validate_bounds catches invalid encounter mode."""
        state = EncounterTacticalState(
            encounter_id="enc:1",
            mode="invalid",
            status="active",
            participants=[],
        )
        violations = EncounterDeterminismValidator.validate_bounds(state)
        assert any("invalid encounter mode" in v for v in violations)

    def test_phase15_validate_bounds_catches_invalid_status(self):
        """Verify validate_bounds catches invalid encounter status."""
        state = EncounterTacticalState(
            encounter_id="enc:1",
            mode="combat",
            status="invalid",
            participants=[],
        )
        violations = EncounterDeterminismValidator.validate_bounds(state)
        assert any("invalid encounter status" in v for v in violations)

    def test_phase15_validate_bounds_catches_turn_order_reference(self):
        """Verify validate_bounds catches turn_order referencing unknown participant."""
        state = EncounterTacticalState(
            encounter_id="enc:1",
            participants=[
                TacticalParticipant(entity_id="a", name="A", initiative=1.0, status="active"),
            ],
            turn_order=["a", "unknown"],
            turn_index=0,
        )
        violations = EncounterDeterminismValidator.validate_bounds(state)
        assert any("turn_order references unknown participant" in v for v in violations)

    def test_phase15_validate_bounds_catches_turn_index_out_of_range(self):
        """Verify validate_bounds catches turn_index out of range."""
        state = EncounterTacticalState(
            encounter_id="enc:1",
            participants=[
                TacticalParticipant(entity_id="a", name="A", initiative=1.0, status="active"),
            ],
            turn_order=["a"],
            turn_index=5,
        )
        violations = EncounterDeterminismValidator.validate_bounds(state)
        assert any("turn_index out of range" in v for v in violations)

    def test_phase15_normalize_state_preserves_participant_order(self):
        """Verify normalize_state preserves participant order."""
        state = EncounterTacticalState(
            participants=[
                TacticalParticipant(entity_id="b", name="B", initiative=1.0, status="active"),
                TacticalParticipant(entity_id="a", name="A", initiative=2.0, status="active"),
            ],
        )
        out = EncounterDeterminismValidator.normalize_state(state)
        assert [p.entity_id for p in out.participants] == ["b", "a"]
        assert out.turn_order == ["a", "b"]

    def test_phase15_normalize_state_clamps_round_number(self):
        """Verify normalize_state clamps round_number to MAX_ROUNDS."""
        state = EncounterTacticalState(
            round_number=MAX_ROUNDS + 100,
            participants=[],
        )
        out = EncounterDeterminismValidator.normalize_state(state)
        assert out.round_number == MAX_ROUNDS

    def test_phase15_normalize_state_validates_participant_status(self):
        """Verify normalize_state resets invalid participant status to active."""
        state = EncounterTacticalState(
            participants=[
                TacticalParticipant(entity_id="a", name="A", initiative=1.0, status="invalid_status"),
            ],
        )
        out = EncounterDeterminismValidator.normalize_state(state)
        assert out.participants[0].status == "active"

    def test_phase15_action_log_item_normalization(self):
        """Verify action_log items are normalized on append."""
        state = EncounterTacticalState(
            participants=[
                TacticalParticipant(entity_id="a", name="A", initiative=1.0, status="active"),
                TacticalParticipant(entity_id="b", name="B", initiative=1.0, status="active"),
            ],
        )
        ActionResolver.resolve_action(
            TacticalAction(action_id="1", actor_id="a", action_type="attack", target_id="b", value=10.0),
            state,
        )
        log_entry = state.action_log[0]
        assert log_entry["action_id"] == "1"
        assert log_entry["action_type"] == "attack"
        assert log_entry["success"] is True
        assert isinstance(log_entry["effects"], list)