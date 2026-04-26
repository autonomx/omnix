from app.rpg.journal.journal_state import add_rumor_journal_entry


def test_add_rumor_journal_entry_is_deduped():
    state = {}
    rumor = {
        "rumor_id": "rumor:old_mill_bandits",
        "title": "Bandits near the old mill",
        "summary": "Travelers have seen armed figures near the old mill road.",
    }

    first = add_rumor_journal_entry(
        state,
        rumor,
        provider_id="npc:Bran",
        provider_name="Bran",
        tick=1,
    )
    second = add_rumor_journal_entry(
        state,
        rumor,
        provider_id="npc:Bran",
        provider_name="Bran",
        tick=2,
    )

    assert first["entry_id"] == "journal:rumor:old_mill_bandits"
    assert second["entry_id"] == "journal:rumor:old_mill_bandits"
    assert len(state["journal_state"]["entries"]) == 1