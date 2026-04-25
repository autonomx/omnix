from app.rpg.memory.service_memory_recall import (
    has_backing_service_memory,
    recall_service_memories,
    recall_service_memories_for_narration,
)


def test_recall_service_memories_filters_by_provider_and_sorts_recent_relevant():
    simulation_state = {
        "memory_state": {
            "service_memories": [
                {
                    "memory_id": "old-bran",
                    "kind": "service_inquiry",
                    "owner_id": "npc:Bran",
                    "owner_name": "Bran",
                    "subject_id": "player",
                    "service_kind": "lodging",
                    "summary": "The player asked Bran about lodging.",
                    "importance": 0.25,
                    "tick": 1,
                },
                {
                    "memory_id": "elara-blocked",
                    "kind": "service_purchase_blocked",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "subject_id": "player",
                    "service_kind": "shop_goods",
                    "offer_id": "elara_rope",
                    "summary": "The player tried to buy Rope from Elara without enough coin.",
                    "blocked_reason": "insufficient_funds",
                    "importance": 0.35,
                    "tick": 20,
                },
                {
                    "memory_id": "elara-inquiry",
                    "kind": "service_inquiry",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "subject_id": "player",
                    "service_kind": "shop_goods",
                    "summary": "The player asked Elara about shop goods.",
                    "importance": 0.25,
                    "tick": 10,
                },
            ]
        }
    }

    recalled = recall_service_memories(
        simulation_state,
        provider_id="npc:Elara",
        service_kind="shop_goods",
        selected_offer_id="elara_rope",
    )

    assert [memory["memory_id"] for memory in recalled] == [
        "elara-blocked",
        "elara-inquiry",
    ]


def test_recall_service_memories_for_narration_uses_service_result_context():
    simulation_state = {
        "memory_state": {
            "service_memories": [
                {
                    "memory_id": "elara-blocked",
                    "kind": "service_purchase_blocked",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "subject_id": "player",
                    "service_kind": "shop_goods",
                    "offer_id": "elara_rope",
                    "summary": "The player tried to buy Rope from Elara without enough coin.",
                    "blocked_reason": "insufficient_funds",
                    "importance": 0.35,
                    "tick": 20,
                }
            ]
        }
    }
    service_result = {
        "matched": True,
        "kind": "service_inquiry",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "selected_offer_id": "",
    }

    payload = recall_service_memories_for_narration(
        simulation_state,
        service_result=service_result,
    )

    assert payload["debug"]["count"] == 1
    assert payload["recalled_service_memories"][0]["memory_id"] == "elara-blocked"


def test_has_backing_service_memory_matches_kind_and_offer():
    memories = [
        {
            "kind": "service_purchase_blocked",
            "service_kind": "shop_goods",
            "offer_id": "elara_rope",
            "blocked_reason": "insufficient_funds",
        }
    ]

    assert has_backing_service_memory(
        memories,
        kinds=["service_purchase_blocked"],
        service_kind="shop_goods",
        offer_id="elara_rope",
    )
    assert not has_backing_service_memory(
        memories,
        kinds=["service_purchase"],
        service_kind="shop_goods",
        offer_id="elara_rope",
    )


def test_recall_service_memories_excludes_current_turn_memory_by_tick_and_id():
    simulation_state = {
        "tick": 20,
        "memory_state": {
            "service_memories": [
                {
                    "memory_id": "prior",
                    "kind": "service_inquiry",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "service_kind": "shop_goods",
                    "summary": "The player asked Elara about shop goods.",
                    "tick": 10,
                },
                {
                    "memory_id": "current",
                    "kind": "service_inquiry",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "service_kind": "shop_goods",
                    "summary": "The player asked Elara about shop goods.",
                    "tick": 20,
                },
            ]
        },
    }

    recalled = recall_service_memories(
        simulation_state,
        provider_id="npc:Elara",
        service_kind="shop_goods",
        current_tick=20,
        exclude_memory_ids=["current"],
    )

    assert [memory["memory_id"] for memory in recalled] == ["prior"]