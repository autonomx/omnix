from __future__ import annotations


def test_addressed_npc_authority_for_direct_question() -> None:
    from app.rpg.session.response_authority import resolve_response_authority

    authority = resolve_response_authority(
        player_input="Bran, do you trust me?",
        intent_result={"kind": "request", "target_id": "npc:bran", "target_name": "Bran", "confidence": "high"},
        world_assessment={"actionability": "respond_only", "state_change_allowed": False},
    )

    assert authority["source"] == "addressed_npc"
    assert authority["id"] == "npc:bran"
    assert authority["display_name"] == "Bran"
    assert "state_mutation" in authority["forbidden_claims"]


def test_narrator_authority_for_observation() -> None:
    from app.rpg.session.response_authority import resolve_response_authority

    authority = resolve_response_authority(
        player_input="I look around",
        intent_result={"kind": "observation", "confidence": "high"},
        world_assessment={"actionability": "observe", "state_change_allowed": False},
    )

    assert authority["source"] == "narrator"
    assert "visible_scene_description" in authority["allowed_claims"]
    assert "mechanical_state_change" in authority["forbidden_claims"]


def test_runtime_authority_for_state_changing_action() -> None:
    from app.rpg.session.response_authority import resolve_response_authority

    authority = resolve_response_authority(
        player_input="I buy ale",
        intent_result={"kind": "buy", "confidence": "high"},
        world_assessment={"actionability": "runtime_action", "state_change_allowed": True},
    )

    assert authority["source"] == "deterministic_runtime"
    assert "currency_transfer" in authority["allowed_claims"]
    assert authority["metadata"]["reason"] == "runtime_required"


def test_system_authority_for_parse_noise() -> None:
    from app.rpg.session.response_authority import resolve_response_authority

    authority = resolve_response_authority(player_input="[object Object]", intent_result={}, world_assessment={})

    assert authority["source"] == "system"
    assert authority["confidence"] == "high"
    assert authority["metadata"]["reason"] == "parse_noise"


def test_system_authority_for_provider_container_parse_noise() -> None:
    from app.rpg.session.response_authority import resolve_response_authority

    for player_input in ("[]", "{}", "tool_calls: []"):
        authority = resolve_response_authority(player_input=player_input, intent_result={}, world_assessment={})

        assert authority["source"] == "system"
        assert authority["metadata"]["reason"] == "parse_noise"


def test_packet_addressed_npc_can_supply_authority_target() -> None:
    from app.rpg.session.response_authority import resolve_response_authority

    authority = resolve_response_authority(
        player_input="Do you remember me?",
        intent_result={"kind": "claim", "confidence": "high"},
        world_assessment={"actionability": "respond_only", "state_change_allowed": False},
        grounding_packet={
            "npc_context": {
                "addressed_npcs": [
                    {"id": "bran", "name": "Bran"},
                ]
            }
        },
    )

    assert authority["source"] == "addressed_npc"
    assert authority["id"] == "npc:bran"
    assert authority["display_name"] == "Bran"
