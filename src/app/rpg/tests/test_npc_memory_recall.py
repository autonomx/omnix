from app.rpg.memory.npc_memory_recall import (
    memory_reference_is_backed,
    recall_npc_memories,
)


def test_recall_npc_memories_excludes_current_tick_and_filters_target():
    state = {
        "memory_state": {
            "service_memories": [
                {
                    "memory_id": "prior-elara",
                    "kind": "service_purchase_blocked",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "subject_id": "player",
                    "service_kind": "shop_goods",
                    "summary": "The player tried to buy Torch from Elara without enough coin.",
                    "blocked_reason": "insufficient_funds",
                    "tick": 10,
                },
                {
                    "memory_id": "current-elara",
                    "kind": "service_inquiry",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "subject_id": "player",
                    "service_kind": "shop_goods",
                    "summary": "The player asked Elara about shop goods.",
                    "tick": 20,
                },
                {
                    "memory_id": "bran",
                    "kind": "service_inquiry",
                    "owner_id": "npc:Bran",
                    "owner_name": "Bran",
                    "subject_id": "player",
                    "service_kind": "lodging",
                    "summary": "The player asked Bran about lodging.",
                    "tick": 5,
                },
            ]
        }
    }

    payload = recall_npc_memories(
        state,
        turn_contract={
            "action": {"target_id": "npc:Elara", "target_name": "Elara"},
            "resolved_result": {"action_type": "social_activity", "target_id": "npc:Elara", "target_name": "Elara"},
        },
        current_tick=20,
        exclude_memory_ids=["current-elara"],
    )

    assert [memory["memory_id"] for memory in payload["recalled_memories"]] == ["prior-elara"]
    assert payload["debug"]["excluded_memory_ids"] == ["current-elara"]


def test_memory_reference_requires_backing():
    memories = [
        {
            "kind": "service_purchase_blocked",
            "summary": "The player tried to buy Torch from Elara without enough coin.",
            "blocked_reason": "insufficient_funds",
        }
    ]

    assert memory_reference_is_backed("Still short on coin from last time?", memories)
    assert not memory_reference_is_backed("You bought this before, remember?", memories)
    assert not memory_reference_is_backed("Still short on coin from last time?", [])