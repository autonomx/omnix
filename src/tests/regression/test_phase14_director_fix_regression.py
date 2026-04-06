"""Regression tests for Phase 14 director fixes."""
from app.rpg.director import (
    DirectorState,
    StoryArcState,
    StoryBeat,
    SceneBiasEngine,
    DirectorDialogueInfluence,
    DirectorQuestInfluence,
    DirectorDeterminismValidator,
)


def test_phase14_normalize_state_clamps_and_sorts_director_state():
    state = DirectorState(
        global_tension=2.0,
        pacing_target=-1.0,
        arcs=[
            StoryArcState(
                arc_id="b",
                title="B",
                phase="invalid",
                tension=2.0,
                priority=0.1,
                status="invalid",
                beats=[StoryBeat(beat_id="2", arc_id="b", beat_type="invalid", status="invalid")],
                focus_entities=["z", "a"],
            ),
            StoryArcState(
                arc_id="a",
                title="A",
                phase="setup",
                tension=0.3,
                priority=0.9,
                status="active",
                beats=[StoryBeat(beat_id="1", arc_id="a", beat_type="event", status="pending")],
            ),
        ],
    )
    out = DirectorDeterminismValidator.normalize_state(state)
    assert out.global_tension == 1.0
    assert out.pacing_target == 0.0
    assert [arc.arc_id for arc in out.arcs] == ["a", "b"]
    assert out.arcs[1].phase == "setup"
    assert out.arcs[1].status == "active"
    assert out.arcs[1].beats[0].beat_type == "event"
    assert out.arcs[1].beats[0].status == "pending"


def test_phase14_director_outputs_are_advisory_and_non_mutating():
    state = DirectorState(
        global_tension=0.8,
        arcs=[
            StoryArcState(
                arc_id="a",
                title="Main Arc",
                phase="rising",
                tension=0.7,
                priority=0.9,
                focus_entities=["npc:guard", "comp:lyra"],
                beats=[StoryBeat(beat_id="b1", arc_id="a", description="Reveal", beat_type="revelation", status="pending")],
            )
        ],
    )
    before = state.to_dict()
    scene_bias = SceneBiasEngine.compute_scene_bias(state)
    dialogue = DirectorDialogueInfluence.get_dialogue_directives(state, "npc:guard", "comp:lyra")
    quest = DirectorQuestInfluence.get_quest_directives(state, [{"quest_id": "q1", "entities": ["npc:guard"]}])
    after = state.to_dict()

    assert before == after
    assert scene_bias["preferred_mood"] == "tense"
    assert "Main Arc" in dialogue["arc_context"]
    assert quest["suggested_priority_quest"] == "q1"