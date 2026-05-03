from tests.rpg.manual.scenarios.registry import build_service_scenarios


def test_campaign_journal_m31_m33_scenarios_are_registered():
    names = set(build_service_scenarios().keys())

    expected = {
        "campaign_journal_records_story_event_entry",
        "campaign_journal_separates_rumor_and_secret_lore",
        "campaign_story_recap_lists_active_arcs_and_pending_consequences",
        "campaign_story_recap_lists_party_member_after_companion_accept",
        "campaign_story_recap_narrator_context_has_rules",
        "campaign_journal_entry_idempotent",
        "campaign_story_recap_is_bounded",
    }

    missing = expected - names
    assert not missing, f"Missing campaign journal scenarios: {sorted(missing)}"