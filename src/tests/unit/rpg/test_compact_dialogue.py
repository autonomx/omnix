from __future__ import annotations

from app.rpg.ai.compact_dialogue import (
    COMPACT_DIALOGUE_SOURCE,
    build_compact_dialogue_advisory,
    is_compact_dialogue_candidate,
)


def _packet(*, addressed: int = 1, combat: bool = False) -> dict:
    profiles = [
        {
            "id": f"npc:{index}",
            "name": "Bran" if index == 0 else "Mira",
            "visible_profile": {"public_biography": "A tavern keeper."},
            "personality_profile": {"summary": "Plain-spoken."},
            "knowledge_boundaries": {"publicly_knows": ["The tavern has regulars."]},
        }
        for index in range(addressed)
    ]
    return {
        "priority_context": {"active_modes": {"combat_active": combat}},
        "npc_context": {"addressed_npcs": profiles},
    }


def test_candidate_accepts_single_addressed_non_stateful_question() -> None:
    assert is_compact_dialogue_candidate(
        player_input="I ask Bran how his day is going.",
        grounding_packet=_packet(),
    )


def test_candidate_rejects_stateful_group_absent_and_combat_turns() -> None:
    for text in (
        "I ask Bran to sell me a drink.",
        "I ask Bran to follow me.",
        "I ask Bran for his private secret.",
        "I ask Bran what food is available.",
        "I threaten Bran.",
    ):
        assert not is_compact_dialogue_candidate(
            player_input=text,
            grounding_packet=_packet(),
        )
    assert not is_compact_dialogue_candidate(
        player_input="I ask Bran and Mira what they think.",
        grounding_packet=_packet(addressed=2),
    )
    assert not is_compact_dialogue_candidate(
        player_input="I call for Bran.",
        grounding_packet=_packet(addressed=0),
    )
    assert not is_compact_dialogue_candidate(
        player_input="I ask Bran how he is.",
        grounding_packet=_packet(combat=True),
    )


def test_build_advisory_uses_one_plain_completion_and_assigns_speaker(monkeypatch) -> None:
    packet = _packet()
    monkeypatch.setattr(
        "app.rpg.ai.compact_dialogue.build_turn_grounding_packet",
        lambda **_kwargs: packet,
    )

    class Gateway:
        calls = []

        def generate(self, prompt, *, provider_options=None):
            self.calls.append((prompt, provider_options))
            return 'Bran: "Steady enough, though the road traffic has thinned."'

    gateway = Gateway()
    advisory = build_compact_dialogue_advisory(
        llm_gateway=gateway,
        player_input="I ask Bran how business is going.",
        simulation_state={},
        runtime_state={},
    )

    assert len(gateway.calls) == 1
    assert gateway.calls[0][1]["max_tokens"] == 80
    assert advisory["source"] == COMPACT_DIALOGUE_SOURCE
    assert advisory["stateful"] is False
    assert advisory["direct_response_gate"]["safe_to_display_now"] is True
    assert advisory["visible_response"]["npc"] == {
        "speaker": "Bran",
        "line": "Steady enough, though the road traffic has thinned.",
    }


def test_build_advisory_uses_authoritative_public_scene_presence(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.ai.compact_dialogue.build_turn_grounding_packet",
        lambda **_kwargs: _packet(addressed=0),
    )

    class Gateway:
        def generate(self, _prompt, *, provider_options=None):
            assert provider_options["max_tokens"] == 80
            return "It has been steady today."

    advisory = build_compact_dialogue_advisory(
        llm_gateway=Gateway(),
        player_input="I ask Bran how business is going.",
        simulation_state={},
        runtime_state={},
        public_state={
            "summary": "Bran, the innkeeper, polishes a cup behind the tavern counter."
        },
    )
    assert advisory["target_name"] == "Bran"
    assert advisory["visible_response"]["npc"]["line"] == "It has been steady today."


def test_public_scene_target_matching_is_case_insensitive_and_canonical(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.ai.compact_dialogue.build_turn_grounding_packet",
        lambda **_kwargs: _packet(addressed=0),
    )

    class Gateway:
        def generate(self, _prompt, *, provider_options=None):
            return "The road has been unusually quiet."

    advisory = build_compact_dialogue_advisory(
        llm_gateway=Gateway(),
        player_input="I ask bran about any rumors lately",
        simulation_state={},
        runtime_state={},
        public_state={"summary": "Bran, the innkeeper, stands behind the counter."},
    )

    assert advisory["target_name"] == "Bran"
    assert advisory["target_id"] == "npc:bran"


def test_public_scene_fallback_rejects_absent_and_group_targets(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.ai.compact_dialogue.build_turn_grounding_packet",
        lambda **_kwargs: _packet(addressed=0),
    )

    class Gateway:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("provider must not be called")

    state = {"summary": "Bran and Mira stand near the tavern counter."}
    for text in (
        "I ask for Bran while he is away.",
        "I ask Bran and Mira what they noticed.",
    ):
        assert build_compact_dialogue_advisory(
            llm_gateway=Gateway(),
            player_input=text,
            simulation_state={},
            runtime_state={},
            public_state=state,
        ) == {}


def test_ambiguous_followup_continues_with_last_concrete_npc(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.ai.compact_dialogue.build_turn_grounding_packet",
        lambda **_kwargs: _packet(addressed=0),
    )

    class Gateway:
        def generate(self, prompt, *, provider_options=None):
            assert '"name":"Bran"' in prompt
            assert "jaw drop" in prompt
            return "Nothing beyond the usual, but I am keeping watch."

    advisory = build_compact_dialogue_advisory(
        llm_gateway=Gateway(),
        player_input="Any troubles lately?",
        simulation_state={},
        runtime_state={
            "last_interaction": {
                "kind": "npc_dialogue",
                "speaker": "Bran",
                "player_input": "How is business?",
                "npc_line": "Rumors that would make your jaw drop.",
            }
        },
        public_state={"summary": "Bran keeps watch behind the tavern counter."},
    )

    assert advisory["target_name"] == "Bran"
    assert advisory["visible_response"]["npc"]["speaker"] == "Bran"


def test_ambiguous_followup_does_not_inherit_generic_scene_speaker(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.ai.compact_dialogue.build_turn_grounding_packet",
        lambda **_kwargs: _packet(addressed=0),
    )

    class Gateway:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("provider must not be called")

    assert build_compact_dialogue_advisory(
        llm_gateway=Gateway(),
        player_input="Any troubles lately?",
        simulation_state={},
        runtime_state={
            "last_interaction": {"kind": "npc_dialogue", "speaker": "General NPCs/Scene"}
        },
        public_state={"summary": "The tavern is busy."},
    ) == {}
