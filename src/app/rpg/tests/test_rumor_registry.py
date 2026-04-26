from app.rpg.world.rumor_registry import get_rumor, select_rumor_for_service


def test_get_rumor():
    rumor = get_rumor("rumor:old_mill_bandits")
    assert rumor["title"] == "Bandits near the old mill"


def test_select_rumor_for_bran_paid_info():
    rumor = select_rumor_for_service(
        {
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "location_id": "loc_tavern",
        },
        {},
    )
    assert rumor["rumor_id"] == "rumor:old_mill_bandits"


def test_select_rumor_skips_known_journal_entry_when_possible():
    rumor = select_rumor_for_service(
        {
            "provider_id": "npc:Bran",
            "provider_name": "Bran",
            "location_id": "loc_tavern",
        },
        {
            "journal_state": {
                "entries": [
                    {
                        "entry_id": "journal:rumor:old_mill_bandits",
                        "source_id": "rumor:old_mill_bandits",
                    }
                ]
            }
        },
    )

    assert rumor
    assert rumor["rumor_id"] != ""