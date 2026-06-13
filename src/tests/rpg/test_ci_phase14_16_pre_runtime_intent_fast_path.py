from __future__ import annotations

from app.rpg.ai.action_intelligence import get_action_advisory
from app.rpg.ai.pre_runtime_intent_fast_path import classify_pre_runtime_intent_fast_path
from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory


class CountingGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        if "semantic intent router" in prompt:
            return '{"action_type":"investigate","semantic_family":"exploration","interaction_mode":"solo","activity_label":"clarify","target_id":"","target_name":"","secondary_actor_ids":[],"visibility":"local","intensity":1,"stakes":1,"social_axes":[],"observer_hooks":[],"scene_impact":"none","stateful":true,"needs_runtime_resolution":true,"visible_response":{},"reason":"semantic provider fallback"}'
        return '{"action_type":"investigate","difficulty":"normal","skill_id":"investigation","intent_tags":["ambiguous"],"narrative_goal":"clarify","target_id":"","target_name":"","stateful":true,"needs_runtime_resolution":true,"visible_response":{},"reason":"provider fallback"}'


def _diag(advisory: dict) -> dict:
    return dict(advisory.get("first_call_grounding_diagnostics") or {})


def test_pre_runtime_fast_path_is_disabled_and_commands_use_llm() -> None:
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

    assert len(gateway.calls) == len(commands)
    assert all(_diag(advisory).get("intent_fast_path_used") is False for advisory in advisories)
    assert all(_diag(advisory).get("intent_llm_used") is True for advisory in advisories)
    assert all(_diag(advisory).get("provider_called") is True for advisory in advisories)
    assert all(_diag(advisory).get("prompt_built") is True for advisory in advisories)
    assert all(_diag(advisory).get("prompt") for advisory in advisories)
    assert all(_diag(advisory).get("prompt_preview") for advisory in advisories)
    assert all(_diag(advisory).get("turn_grounding_packet") for advisory in advisories)
    assert {advisory["action_type"] for advisory in advisories} == {"investigate"}


def test_disabled_fast_path_builds_prompt_and_grounding_packet() -> None:
    gateway = CountingGateway()

    advisory = get_action_advisory(
        llm_gateway=gateway,
        player_input="I ask Bran to remember the warning phrase.",
        simulation_state={"expensive": object()},
        runtime_state={"expensive": object()},
        candidate_action={},
    )

    diagnostics = _diag(advisory)
    assert len(gateway.calls) == 1
    assert diagnostics.get("provider_status") == "valid_json"
    assert diagnostics.get("intent_fast_path_used") is False
    assert diagnostics.get("intent_llm_used") is True
    assert diagnostics.get("prompt_built") is True
    assert diagnostics.get("prompt_available") is True
    assert diagnostics.get("prompt")
    assert diagnostics.get("prompt_preview")
    assert diagnostics.get("turn_grounding_packet")


def test_semantic_router_uses_provider_when_action_fast_path_is_disabled() -> None:
    gateway = CountingGateway()
    action_advisory = get_action_advisory(
        llm_gateway=gateway,
        player_input="I leave the Rusty Flagon and take the road toward the quarry.",
        simulation_state={"expensive": object()},
        runtime_state={"expensive": object()},
        candidate_action={},
    )

    semantic_advisory = get_semantic_action_advisory(
        llm_gateway=gateway,
        player_input="I leave the Rusty Flagon and take the road toward the quarry.",
        simulation_state={"expensive": object()},
        runtime_state={"expensive": object()},
        candidate_action=action_advisory,
    )

    diagnostics = _diag(semantic_advisory)
    assert len(gateway.calls) == 2
    assert semantic_advisory["action_type"] == "investigate"
    assert semantic_advisory["semantic_family"] == "exploration"
    assert diagnostics.get("semantic_fast_path_used") is False
    assert diagnostics.get("semantic_llm_used") is True
    assert diagnostics.get("provider_called") is True
    assert diagnostics.get("provider_requested") is True
    assert diagnostics.get("provider_status") == "valid_json"
    assert diagnostics.get("semantic_prompt_built") is True
    assert diagnostics.get("prompt")
    assert diagnostics.get("prompt_preview")
    assert diagnostics.get("turn_grounding_packet")


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


def test_direct_npc_opinion_question_declines_fast_path_for_llm_dialogue() -> None:
    gateway = CountingGateway()
    advisory = get_action_advisory(
        llm_gateway=gateway,
        player_input="Bran, what do you think about sword combat styles?",
        simulation_state={},
        runtime_state={},
        candidate_action={},
    )

    diagnostics = _diag(advisory)

    assert len(gateway.calls) == 1
    assert diagnostics.get("intent_fast_path_used") is False
    assert diagnostics.get("intent_llm_used") is True
    assert diagnostics.get("provider_called") is True
    assert advisory["action_type"] == "investigate"


def test_semantic_router_still_calls_provider_for_ambiguous_action() -> None:
    gateway = CountingGateway()
    semantic_advisory = get_semantic_action_advisory(
        llm_gateway=gateway,
        player_input="I do the thing from before, but carefully.",
        simulation_state={},
        runtime_state={},
        candidate_action={},
    )

    diagnostics = _diag(semantic_advisory)
    assert len(gateway.calls) == 1
    assert "semantic intent router" in gateway.calls[0]
    assert diagnostics.get("semantic_fast_path_used") is False
    assert diagnostics.get("semantic_llm_used") is True
    assert diagnostics.get("provider_called") is True
    assert diagnostics.get("prompt_built") is True
    assert semantic_advisory["action_type"] == "investigate"


def test_fast_path_helper_declines_empty_or_ambiguous_text() -> None:
    assert classify_pre_runtime_intent_fast_path(player_input="", candidate_action={}) == {}
    assert classify_pre_runtime_intent_fast_path(player_input="Maybe that one.", candidate_action={}) == {}
    assert classify_pre_runtime_intent_fast_path(player_input="I attack the bandit.", candidate_action={}) == {}
