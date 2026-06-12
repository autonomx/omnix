from __future__ import annotations

from app.rpg.session.player_agency_contract import (
    attach_player_agency_contract,
    build_player_agency_contract,
    build_authoritative_next_action_candidates,
    flavor_player_agency_options,
    infer_player_personality,
)


class MaliciousFlavorProvider:
    def generate(self, prompt: str, context: dict, timeout_s: float = 20.0) -> str:
        return '{"options":[{"id":"talk-current-npc","label":"Lean on Bran until he cracks","description":"Let your colder instincts color the question, but the action still has to go through runtime.","command":"I assassinate Bran.","action_type":"combat","tone_tags":["dark","coercive"]},{"id":"invented-option","label":"Impossible","description":"Should be ignored","tone_tags":["bad"]}]}'


def _sample_result() -> dict:
    return {
        "ok": True,
        "npc": {"id": "npc:bran", "speaker": "Bran", "line": "Road's not kind tonight."},
        "simulation_state": {
            "current_location_id": "loc:rusty_flagon",
            "location_name": "Rusty Flagon",
            "player_state": {
                "inventory_state": {
                    "items": [{"item_id": "trail_ration", "quantity": 1}],
                    "currency": {"silver": 10},
                },
                "personality": {"alignment": "evil", "traits": ["ruthless", "patient"]},
            },
        },
        "runtime_state": {"current_objective": "Follow the bandit clue toward the old quarry."},
    }


def test_authoritative_next_action_candidates_are_bounded_and_state_relevant() -> None:
    options = build_authoritative_next_action_candidates(result=_sample_result(), max_options=5)

    assert 1 <= len(options) <= 5
    ids = {option["id"] for option in options}
    assert "talk-current-npc" in ids
    assert "inspect-location" in ids
    assert "service-or-supplies" in ids or "check-inventory" in ids
    assert all(option["validation_required"] is True for option in options)
    assert all(option["presentation_only"] is True for option in options)
    assert all(option["command"] for option in options)


def test_personality_inference_detects_dark_player_tone() -> None:
    personality = infer_player_personality(result=_sample_result())

    assert personality["tone_hint"] == "dark"
    assert "evil" in personality["descriptor"]
    assert "ruthless" in personality["descriptor"]


def test_llm_flavor_can_change_tone_but_not_command_or_action_type() -> None:
    base = build_authoritative_next_action_candidates(result=_sample_result(), max_options=5)
    original_by_id = {option["id"]: dict(option) for option in base}

    flavored, diagnostics = flavor_player_agency_options(
        options=base,
        player_personality={"descriptor": "alignment: evil; traits: ruthless", "tone_hint": "dark"},
        provider=MaliciousFlavorProvider(),
    )

    assert diagnostics["requested"] is True
    assert diagnostics["provider_called"] is True
    assert diagnostics["applied"] is True
    by_id = {option["id"]: option for option in flavored}
    assert "invented-option" not in by_id
    assert by_id["talk-current-npc"]["label"] == "Lean on Bran until he cracks"
    assert "dark" in by_id["talk-current-npc"]["tone_tags"]
    assert by_id["talk-current-npc"]["command"] == original_by_id["talk-current-npc"]["command"]
    assert by_id["talk-current-npc"]["action_type"] == original_by_id["talk-current-npc"]["action_type"]
    assert by_id["talk-current-npc"]["target_id"] == original_by_id["talk-current-npc"]["target_id"]


def test_build_contract_includes_safety_and_personality_flavored_options() -> None:
    contract = build_player_agency_contract(
        player_input="What now?",
        result=_sample_result(),
        provider=MaliciousFlavorProvider(),
    )

    assert contract["format_version"] == "rpg_player_agency_contract_v1"
    assert contract["option_count"] == len(contract["options"])
    assert contract["personality"]["tone_hint"] == "dark"
    assert contract["safety"]["runtime_validation_required"] is True
    assert contract["safety"]["llm_may_not_change_commands_or_action_types"] is True
    assert any("dark" in option.get("tone_tags", []) for option in contract["options"])


def test_attach_player_agency_contract_adds_top_level_and_nested_payload() -> None:
    result = {"ok": True, "result": {"summary": "You wait."}, **_sample_result()}

    updated = attach_player_agency_contract(result, player_input="What can I do next?")

    assert "next_actions" in updated
    assert "player_agency_contract" in updated
    assert updated["next_actions"]["option_count"] >= 1
    assert updated["result"]["next_actions"]["format_version"] == "rpg_player_agency_contract_v1"
