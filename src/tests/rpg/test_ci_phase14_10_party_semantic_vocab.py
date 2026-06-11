from __future__ import annotations

from tests.rpg import interactive_cli_live_llm_playtest as playtest


def _transcript(*narrations: str) -> dict:
    return {
        "turns": [
            {
                "turn_index": index,
                "player_input": f"scripted command {index}",
                "raw_narration": narration,
                "narration_source": "provider_runtime_narration",
                "narration_status": "completed",
                "llm_called": True,
                "interactive_cli_state_bundle": {"ok": True},
            }
            for index, narration in enumerate(narrations, start=1)
        ]
    }


def test_phase14_10_party_semantics_accept_accompany_wording_from_live_run() -> None:
    result = playtest.evaluate_live_mechanic_semantics(
        _transcript(
            "Bran nods solemnly. Agreed, he states, his voice steady. I will accompany you.",
            "The tavern now feels livelier with his presence.",
        ),
        scenario_pack="party-companion",
    )

    assert result["ok"] is True
    assert result["missing_count"] == 0
    assert result["failures"] == []
    assert result["matched"]["companion_or_party"]["matched_phrase"] == "accompany"


def test_phase14_10_party_semantics_accept_company_wording_without_party_keyword() -> None:
    result = playtest.evaluate_live_mechanic_semantics(
        _transcript("For that, you would have my company, Bran says."),
        scenario_pack="party-companion",
    )

    assert result["ok"] is True
    assert result["matched"]["companion_or_party"]["matched_phrase"] == "company"
