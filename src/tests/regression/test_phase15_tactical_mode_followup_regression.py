"""Phase 15 — Tactical Mode Follow-up Regression Tests.

Tests for participant order preservation and active effects derivation.
"""

from app.rpg.encounter.tactical_mode import (
    EncounterTacticalState,
    TacticalParticipant,
    CombatEffect,
    EncounterDeterminismValidator,
)


class TestPhase15TacticalModeFollowupRegression:
    """Regression tests for Phase 15 tactical mode follow-up fixes."""

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

    def test_phase15_active_effects_are_rebuilt_from_participants(self):
        """Verify active_effects are rebuilt from participants."""
        state = EncounterTacticalState(
            participants=[
                TacticalParticipant(
                    entity_id="a",
                    name="A",
                    initiative=1.0,
                    status="active",
                    effects=[
                        CombatEffect(
                            effect_id="eff1",
                            effect_type="damage",
                            target_id="a",
                            value=2.0,
                            duration=2,
                            remaining=1,
                            source_id="b",
                        )
                    ],
                )
            ],
            active_effects=[],
        )
        out = EncounterDeterminismValidator.normalize_state(state)
        assert len(out.active_effects) == 1
        assert out.active_effects[0].effect_id == "eff1"