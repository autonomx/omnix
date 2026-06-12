from __future__ import annotations

import pytest

from app.rpg.ai import action_intelligence
from app.rpg.ai.action_intelligence import get_action_advisory
from app.rpg.ai.pre_runtime_intent_fast_path import classify_pre_runtime_intent_fast_path


class CountingGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return '{"action_type":"investigate","difficulty":"normal","skill_id":"investigation","intent_tags":["ambiguous"],"narrative_goal":"clarify","target_id":"","target_name":"","stateful":true,"needs_runtime_resolution":true,"visible_response":{},"reason":"provider fallback"}'


def _diag(advisory: dict) -> dict:
    return dict(advisory.get("first_call_grounding_diagnostics") or {})


def test_fast_path_classifies_endurance_style_commands_without_llm() -> None:
    gateway = CountingGateway()
    commands = [
        "I ask Bran to travel with me as a companion for a longer job.",
        "I buy or rent what I can afford and check my coin afterward.",
        "I leave the Rusty Flagon and take the road toward the quarry.",
        "I inspect the muddy tracks for a useful lead.",
        "I defend myself and choose a careful attack.",
        "I tell Bran a private code phrase: silver owl.",
    ]

    advisories = [
        get_action_advisory(
            llm_gateway=gateway,
            player_input=command,
            simulation_state={},
            runtime_state={},
            candidate_action={},
        )
        for command in commands
    ]

    assert gateway.calls == []
    assert all(_diag(advisory).get("intent_fast_path_used") is True for advisory in advisories)
    assert all(_diag(advisory).get("intent_llm_used") is False for advisory in advisories)
    assert all(_diag(advisory).get("provider_called") is False for advisory in advisories)
    assert all(_diag(advisory).get("prompt_built") is False for advisory in advisories)
    assert all(_diag(advisory).get("prompt") == "" for advisory in advisories)
    assert all(_diag(advisory).get("prompt_preview") == "" for advisory in advisories)
    assert all(_diag(advisory).get("turn_grounding_packet") == {} for advisory in advisories)
    assert {advisory["action_type"] for advisory in advisories} >= {
        "social_activity",
        "trade",
        "exploration",
        "investigate",
        "attack_melee",
    }


def test_fast_path_skips_prompt_and_grounding_packet_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_prompt_is_built(*args: object, **kwargs: object) -> dict:
        raise AssertionError("fast path should not build turn grounding packet")

    monkeypatch.setattr(action_intelligence, "build_turn_grounding_packet", fail_if_prompt_is_built)
    gateway = CountingGateway()

    advisory = get_action_advisory(
        llm_gateway=gateway,
        player_input="I ask Bran to remember the warning phrase.",
        simulation_state={"expensive": object()},
        runtime_state={"expensive": object()},
        candidate_action={},
    )

    diagnostics = _diag(advisory)
    assert gateway.calls == []
    assert diagnostics.get("provider_status") == "fast_path"
    assert diagnostics.get("prompt_built") is False
    assert diagnostics.get("prompt_available") is False
    assert diagnostics.get("prompt") == ""
    assert diagnostics.get("prompt_preview") == ""
    assert diagnostics.get("turn_grounding_packet") == {}


def test_ambiguous_input_still_falls_back_to_provider_classifier() -> None:
    gateway = CountingGateway()
    advisory = get_action_advisory(
        llm_gateway=gateway,
        player_input="I do the thing from before, but carefully.",
        simulation_state={},
        runtime_state={},
        candidate_action={},
    )

    diagnostics = _diag(advisory)
    assert len(gateway.calls) == 1
    assert "INPUT:\n" in gateway.calls[0]
    assert diagnostics.get("intent_fast_path_used") is False
    assert diagnostics.get("intent_llm_used") is True
    assert diagnostics.get("provider_called") is True
    assert diagnostics.get("prompt_built") is True
    assert diagnostics.get("prompt_preview")
    assert advisory["action_type"] == "investigate"


def test_fast_path_helper_declines_empty_or_ambiguous_text() -> None:
    assert classify_pre_runtime_intent_fast_path(player_input="", candidate_action={}) == {}
    assert classify_pre_runtime_intent_fast_path(player_input="Maybe that one.", candidate_action={}) == {}
