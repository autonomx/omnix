from app.rpg.campaign_journal.journal import record_campaign_journal_entry
from app.rpg.lore.state import upsert_lore_entry
from app.rpg.story_authoring.prompts import build_story_authoring_prompt


def test_story_authoring_prompt_contains_recap_and_constraints():
    simulation_state = {}
    record_campaign_journal_entry(
        simulation_state,
        kind="story_event",
        summary="Bandit rumors reached the tavern.",
        turn_index=1,
        source_id="event:rumor",
    )

    prompt = build_story_authoring_prompt(
        simulation_state,
        authoring_goal="Create an escalation pack.",
        turn_index=2,
    )

    assert "Return JSON only" in prompt["user"]
    assert "campaign_recap" in prompt["user"]
    assert "story_proposal_v1" in prompt["user"]


def test_story_authoring_prompt_does_not_surface_unrevealed_secret_lore():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:secret_debt",
            "title": "Secret Debt",
            "truth_status": "secret",
            "revealed_to_player": False,
            "summary": "Bran secretly owes the Red Sashes.",
        },
    )

    prompt = build_story_authoring_prompt(
        simulation_state,
        authoring_goal="Create a story pack.",
        turn_index=2,
    )

    assert "Bran secretly owes the Red Sashes." not in prompt["user"]