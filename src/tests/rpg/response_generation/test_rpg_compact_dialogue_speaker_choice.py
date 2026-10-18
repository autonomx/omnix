"""The model names who the player addresses ("the bartender") among present NPCs, in the one dialogue call."""
from __future__ import annotations

import json

from app.apps.rpg.session.compact_dialogue import build_compact_dialogue_advisory


def _state() -> tuple[dict, dict]:
    simulation = {
        "npc_index": {
            "npc:bran": {"name": "Bran", "role": "bartender", "description": "Keeps the bar of the Rusty Flagon."},
            "npc:mira": {"name": "Mira", "role": "traveling bard", "description": "Tunes a lute by the hearth."},
        },
        "scene": {"location_name": "The Rusty Flagon", "present_npc_ids": ["npc:bran", "npc:mira"]},
    }
    return simulation, {}


class _Gateway:
    def __init__(self, answer: dict | str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def generate(self, prompt, **_kwargs):
        self.prompts.append(prompt)
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


def test_the_model_chooses_the_addressed_npc_and_answers_as_them() -> None:
    simulation, runtime = _state()
    gateway = _Gateway({"speaker_id": "npc:bran", "line": "Evening, traveler. What can I pour you?"})

    advisory = build_compact_dialogue_advisory(
        llm_gateway=gateway, player_input="talk to the bartender",
        simulation_state=simulation, runtime_state=runtime,
    )

    assert len(gateway.prompts) == 1
    assert '"present_npcs"' in gateway.prompts[0] and "bartender" in gateway.prompts[0]
    assert advisory["target_id"] == "npc:bran"
    assert advisory["visible_response"]["npc"] == {"speaker": "Bran", "line": "Evening, traveler. What can I pour you?"}


def test_an_unknown_speaker_falls_back_to_the_full_semantic_path() -> None:
    simulation, runtime = _state()
    for answer in ({"speaker_id": "npc:the", "line": "Hello."}, "not json", {"speaker_id": "npc:bran", "line": ""}):
        assert build_compact_dialogue_advisory(
            llm_gateway=_Gateway(answer), player_input="talk to the bartender",
            simulation_state=simulation, runtime_state=runtime,
        ) == {}
