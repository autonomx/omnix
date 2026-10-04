from __future__ import annotations

from app.rpg.presentation.dialogue_quality import enforce_dialogue_quality


def test_llm_dialogue_is_never_replaced_by_deterministic_quality_fallback() -> None:
    provider_line = (
        "I am here because the seawall manifests do not match the cargo "
        "moving through Tidebreak."
    )
    result = {
        "ok": True,
        "llm_called": True,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "visible_response": {
            "narration": "Juno glances toward the working cranes.",
            "npc": {"speaker": "Juno Rask", "line": provider_line},
        },
    }

    enforced = enforce_dialogue_quality(
        result,
        session={"state": {"current_location_name": "Tidebreak Docks"}},
        player_input="I ask Juno what she is doing here",
    )

    assert enforced["npc"]["line"] == provider_line
    assert enforced["dialogue_quality"]["repaired"] is False
    assert enforced["dialogue_quality"]["provider_authored"] is True
    assert (
        enforced["dialogue_quality"]["repair_source"]
        == "provider_visible_response_preserved_llm_only_policy_v1"
    )
    assert enforced["dialogue_quality"]["deterministic_replacement_forbidden"] is True
