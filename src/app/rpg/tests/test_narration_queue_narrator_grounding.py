"""Tests for narration job queue functionality."""
import json
from unittest.mock import patch




def test_accommodation_dialogue_does_not_invent_room_offer_without_service_result():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def call(self, method, *args, **kwargs):
            if method == "generate_stream":
                return self.generate_stream(*args, **kwargs)
            if method == "generate":
                return {
                    "text": (
                        '{"format_version":"rpg_narration_v2",'
                        '"narration":"Bran looks up from behind the counter.",'
                        '"action":"Bran considers your request.",'
                        '"npc":{"speaker":"Bran","line":"A room, you say? Well, we do have a few vacant rooms available on the top floor with the best view in town."},'
                        '"reward":"","followup_hooks":[]}'
                    )
                }
            return {}

        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran looks up from behind the counter.",'
                    '"action":"Bran considers your request.",'
                    '"npc":{"speaker":"Bran","line":"A room, you say? Well, we do have a few vacant rooms available on the top floor with the best view in town."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }
    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "semantic_action": {
                "action_type": "trade",
                "activity_label": "request_accommodation",
                "target_name": "Bran",
            },
            "narration_brief": {"summary": "I ask Bran for a room to rent"},
            "resolved_result": {
                "action_metadata": {
                    "transaction_kind": "",
                    "price_source": "",
                    "provider_id": "",
                    "provider_name": "",
                },
                "effect_result": {"service_effects": {}},
            },
        },
        "resolved_result": {
            "ok": True,
            "target_name": "Bran",
            "action_metadata": {
                "transaction_kind": "",
                "price_source": "",
                "provider_id": "",
                "provider_name": "",
            },
            "effect_result": {"service_effects": {}},
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )
    text = result["narration"].lower()

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran considers your request" in text
    assert "vacant rooms" not in text
    assert "top floor" not in text
    assert "best view" not in text
    assert "let me check what i can offer" in text

def test_accommodation_grounding_catches_cozy_room_and_cost_invention():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"The tavern quiets as Bran looks your way.",'
                    '"action":"With a hopeful glint in your eye, you approach Bran and ask if he has a room to rent.",'
                    '"npc":{"speaker":"Bran","line":"Aye, I\\\'ve got a cozy little room above the inn, perfect for a traveler such as yourself. What\\\'ll it cost you?"},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }

    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "semantic_action": {
                "action_type": "social_activity",
                "activity_label": "requesting_rental",
                "target_name": "Bran",
                "reason": "rent_room",
            },
            "narration_brief": {
                "summary": "I ask Bran for a room to rent",
            },
            "resolved_result": {
                "action_metadata": {
                    "transaction_kind": "",
                    "price_source": "",
                    "provider_id": "",
                    "provider_name": "",
                },
                "effect_result": {
                    "service_effects": {},
                },
            },
        },
        "resolved_result": {
            "outcome": "success",
            "target_name": "Bran",
            "action_metadata": {
                "transaction_kind": "",
                "price_source": "",
                "provider_id": "",
                "provider_name": "",
            },
            "effect_result": {
                "service_effects": {},
            },
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran considers your request" in text

    assert "cozy little room" not in text
    assert "above the inn" not in text
    assert "perfect for a traveler" not in text
    assert "what'll it cost" not in text
    assert "cost you" not in text

    assert "let me check what i can offer" in text

def test_live_narrator_renders_authoritative_action_and_preserves_npc_dialogue():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    full_line = (
        "Ah, you're looking to rent a room, eh? We've got a cozy little number "
        "on the top floor, just down the hall from the kitchen. It's the best "
        "view in town, aside from the garden out back."
    )

    class StubGateway:
        def call(self, method, *args, **kwargs):
            if method == "generate_stream":
                return self.generate_stream(*args, **kwargs)
            elif method == "generate":
                return {"text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"You approach the innkeeper as you inquire about available lodgings.",'
                    '"action":"Bran nods thoughtfully as he considers your request.",'
                    f'"npc":{{"speaker":"Bran","line":{json.dumps(full_line)}}},'
                    '"reward":"","followup_hooks":[]}'
                )}
            return {}

        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"You approach the innkeeper as you inquire about available lodgings.",'
                    '"action":"Bran nods thoughtfully as he considers your request.",'
                    f'"npc":{{"speaker":"Bran","line":{json.dumps(full_line)}}},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }
    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "narration_brief": {"summary": "I ask Bran for a room to rent"},
        },
        "resolved_result": {"ok": True, "target_name": "Bran"},
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]

    assert "Action: You ask Bran for a room to rent" in text
    assert "Result: Bran nods thoughtfully as he considers your request." in text
    assert full_line in text
    assert "kitc..." not in text

def test_narrate_scene_does_not_emit_format_invalid_on_non_json_llm_text():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    llm_output = "Bran narrows his eyes. A room is five silver."

    with patch("app.rpg.ai.world_scene_narrator._generate_live_narrative", return_value=llm_output):
        result = narrate_scene(
            {"title": "The Rusty Flagon Tavern"},
            {"player_input": "how much for a room?"},
            llm_gateway=object(),
        )

    assert "[ERROR: LLM FORMAT INVALID]" not in result.get("narration", "")
    assert result.get("used_llm") is True

def test_narrate_scene_force_sync_can_fallback_when_provider_fails():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class FailingGateway:
        def generate(self, *args, **kwargs):
            raise RuntimeError("provider_down")

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern"},
        {
            "player_input": "I wait",
            "force_sync_narration": True,
            "resolved_result": {"ok": True, "message": "You wait and watch the room."},
        },
        llm_gateway=FailingGateway(),
        retry_on_invalid=False,
    )

    assert result.get("used_llm") is True
    assert "You wait and watch the room." in result.get("narration", "")

def test_assemble_turn_narration_response_sync_does_not_force_live_llm():
    from app.rpg.session.narration_runtime import assemble_turn_narration_response

    captured = {}

    def _fake_narrate_scene(scene, narration_context, llm_gateway=None):
        captured["scene"] = scene
        captured["narration_context"] = narration_context
        return {
            "narration": "You wait and watch the room.",
            "narration_json": {"narration": "You wait and watch the room."},
            "used_llm": False,
        }

    with patch("app.rpg.session.narration_runtime.narrate_scene", side_effect=_fake_narrate_scene), \
         patch("app.rpg.session.narration_runtime.build_app_llm_gateway", return_value=object()):
        result = assemble_turn_narration_response(
            session={"session_id": "test_session"},
            authoritative={},
            turn_contract={},
            narration_request={
                "scene": {"title": "The Rusty Flagon Tavern"},
                "narration_context": {"player_input": "I wait"},
            },
            runtime_state={
                "force_sync_narration": True,
                "performance": {},
                "runtime_settings": {},
            },
            perf={"enable_live_narration_llm": True},
            resolved_result={"ok": True, "message": "You wait and watch the room."},
        )

    assert result["result"]["narration"] == "You wait and watch the room."
    assert captured["narration_context"]["force_sync_narration"] is True
    assert captured["narration_context"]["require_live_llm_narration"] is False

def test_assemble_turn_narration_response_sync_recomputes_service_recall_when_missing():
    from app.rpg.session.narration_runtime import assemble_turn_narration_response

    captured = {}

    def _fake_narrate_scene(scene, narration_context, llm_gateway=None):
        captured["narration_context"] = narration_context
        return {
            "narration": "Elara recognizes the earlier failed purchase.",
            "narration_json": {"narration": "Elara recognizes the earlier failed purchase."},
            "used_llm": False,
        }

    with patch("app.rpg.session.narration_runtime.narrate_scene", side_effect=_fake_narrate_scene), \
         patch("app.rpg.session.narration_runtime.build_app_llm_gateway", return_value=object()):
        result = assemble_turn_narration_response(
            session={"session_id": "test_session"},
            authoritative={},
            turn_contract={},
            narration_request={
                "scene": {"title": "Market Stall"},
                "narration_context": {
                    "player_input": "I buy Torch from Elara",
                    "simulation_state": {
                        "memory_state": {
                            "service_memories": [
                                {
                                    "memory_id": "memory:test",
                                    "kind": "service_purchase_blocked",
                                    "owner_id": "npc:Elara",
                                    "owner_name": "Elara",
                                    "subject_id": "player",
                                    "service_kind": "shop_goods",
                                    "offer_id": "elara_torch",
                                    "summary": "The player tried to buy Torch from Elara without enough coin.",
                                    "blocked_reason": "insufficient_funds",
                                    "importance": 0.35,
                                    "tick": 20,
                                }
                            ]
                        }
                    },
                },
            },
            runtime_state={
                "force_sync_narration": True,
                "performance": {},
                "runtime_settings": {},
            },
            perf={"enable_live_narration_llm": True},
            resolved_result={
                "service_result": {
                    "matched": True,
                    "kind": "service_purchase",
                    "service_kind": "shop_goods",
                    "provider_id": "npc:Elara",
                    "provider_name": "Elara",
                    "selected_offer_id": "elara_torch",
                }
            },
        )

    assert result["result"]["narration"] == "Elara recognizes the earlier failed purchase."
    assert len(captured["narration_context"]["recalled_service_memories"]) == 1
    assert captured["narration_context"]["service_memory_recall_debug"]["count"] == 1

def test_assemble_turn_narration_response_sync_preserves_structural_result_fields_without_authoritative_envelope():
    from app.rpg.session.narration_runtime import assemble_turn_narration_response

    with patch("app.rpg.session.narration_runtime.narrate_scene", return_value={
        "narration": "Bran quotes the meal options.",
        "narration_json": {"narration": "Bran quotes the meal options."},
        "used_llm": False,
    }), patch("app.rpg.session.narration_runtime.build_app_llm_gateway", return_value=object()):
        result = assemble_turn_narration_response(
            session={"session_id": "test_session"},
            authoritative={},
            turn_contract={
                "presentation": {"available_actions": [{"action_id": "service:purchase:bran_meal_stew"}]},
                "narration_brief": {"summary": "Bran offers a bowl of stew."},
            },
            narration_request={
                "turn_id": "turn:42",
                "tick": 42,
                "scene": {"title": "The Rusty Flagon Tavern"},
                "narration_context": {"player_input": "I ask Bran for food"},
            },
            runtime_state={
                "force_sync_narration": True,
                "performance": {},
                "runtime_settings": {"response_length": "short"},
                "last_turn_result": {
                    "combat_result": {"status": "idle"},
                    "xp_result": {"player_xp": 1},
                    "skill_xp_result": {"awards": {}},
                    "level_up": [],
                    "skill_level_ups": [],
                    "summary": ["Bran offers a bowl of stew."],
                },
            },
            perf={"enable_live_narration_llm": True},
            resolved_result={
                "service_result": {
                    "matched": True,
                    "kind": "service_inquiry",
                    "service_kind": "meal",
                    "provider_id": "npc:Bran",
                    "provider_name": "Bran",
                },
                "memory_state": {"service_memories": [{"memory_id": "memory:current"}]},
            },
        )

    assert result["result"]["turn_id"] == "turn:42"
    assert result["result"]["tick"] == 42
    assert result["result"]["resolved_result"]["memory_state"]["service_memories"][0]["memory_id"] == "memory:current"
    assert result["result"]["xp_result"]["player_xp"] == 1
    assert result["result"]["presentation"]["available_actions"][0]["action_id"] == "service:purchase:bran_meal_stew"
    assert result["result"]["response_length"] == "short"

def test_narrator_reward_and_action_are_authoritative_only():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"The tavern goes quiet.","action":"You win a fortune.","npc":{"speaker":"Bran the Innkeeper","line":"Take this chest of gold."},"reward":"25 gold and merchant reputation","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "Bran quotes a price for the room.",
            "target_name": "Bran the Innkeeper",
            "dialogue": "A room costs five silver pieces, up front.",
        },
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]
    assert "fortune" not in text.lower()
    assert "25 gold" not in text.lower()
    assert "merchant reputation" not in text.lower()
    assert "Bran quotes a price for the room." in text

def test_narrator_rejects_invented_npc_speaker():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"The town guard Captain steps forward. Captain of the Town Guard says: \"Seize him.\"","action":"You insult Bran.","npc":{"speaker":"Captain of the Town Guard","line":"Seize him"},"reward":"","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "Bran scowls at your insult.",
            "target_name": "Bran the Innkeeper",
        },
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]
    assert "Captain of the Town Guard" not in text
    assert "Seize him" not in text

def test_narrator_respects_recent_authoritative_room_price():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"Bran names a price of ten gold coins for the room.","action":"You ask about the room price.","npc":{"speaker":"Bran the Innkeeper","line":"Ten gold for the night."},"reward":"","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "You ask Bran how much the room costs.",
            "target_name": "Bran the Innkeeper",
            "dialogue": "A room costs five silver pieces, up front.",
        },
        "recent_authoritative_facts": [
            'Tick 2: Bran quotes a price for the room. | Bran the Innkeeper said: "A room costs five silver pieces, up front."'
        ],
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]
    assert "ten gold" not in text.lower()
    assert "five silver" in text.lower()

def test_narrator_rejects_invented_guards_and_guilds_from_narration_text():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"Elara signals the guards and word spreads through the merchant guild.","action":"You insult Bran.","npc":{"speaker":"Bran the Innkeeper","line":"Watch your tongue."},"reward":"","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "Bran scowls at your insult.",
            "target_name": "Bran the Innkeeper",
        },
        "recent_authoritative_facts": [
            "Tick 4: Bran scowls at your insult."
        ],
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"].lower()
    assert "guards" not in text
    assert "merchant guild" not in text

def test_normalize_final_narration_text_preserves_dialogue_ellipsis():
    from app.rpg.session.runtime import _normalize_final_narration_text

    value = _normalize_final_narration_text(
        'Bran: "I was thinking..."'
    )

    assert value == 'Bran: "I was thinking..."'

def test_normalize_final_narration_text_adds_terminal_punctuation():
    from app.rpg.session.runtime import _normalize_final_narration_text

    value = _normalize_final_narration_text(
        "Bran the Innkeeper names his price"
    )

    assert value == "Bran the Innkeeper names his price."

def test_accommodation_grounding_blocks_vacancy_and_follow_me_claims():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"The inn common room quiets as Bran looks your way.",'
                    '"action":"You ask Bran for a room to rent, your persuasive voice carrying across the room.",'
                    '"npc":{"speaker":"Bran","line":"A room, you say? Well, we haven\\\'t had any vacancies lately, but I might have somethin\\\' for you. Follow me."},'
                    '"reward":"+6 persuasion XP","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }

    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "semantic_action": {
                "action_type": "social_activity",
                "activity_label": "asking_for_room_rental",
                "target_name": "Bran",
                "reason": "asking_for_room_rental",
            },
            "narration_brief": {
                "summary": "I ask Bran for a room to rent",
            },
            "resolved_result": {
                "action_metadata": {
                    "transaction_kind": "",
                    "price_source": "",
                    "provider_id": "",
                    "provider_name": "",
                },
                "effect_result": {
                    "service_effects": {},
                },
            },
        },
        "resolved_result": {
            "outcome": "success",
            "target_name": "Bran",
            "action_metadata": {
                "transaction_kind": "",
                "price_source": "",
                "provider_id": "",
                "provider_name": "",
            },
            "effect_result": {
                "service_effects": {},
            },
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran considers your request" in text

    assert "vacancies" not in text
    assert "might have somethin" not in text
    assert "something for you" not in text
    assert "follow me" not in text

    assert "let me check what i can offer" in text
    assert narration_json["reward"] == ""

def test_service_narration_uses_registered_lodging_offers():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran watches you from behind the counter.",'
                    '"action":"You politely inquire about renting a room from Bran.",'
                    '"npc":{"speaker":"Bran","line":"Rooms, you say? I have a few, but they are not cheap."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }

    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "lodging",
                "provider_id": "npc:Bran",
                "provider_name": "Bran",
                "location_id": "loc_tavern",
                "status": "offers_available",
                "offers": [
                    {
                        "offer_id": "bran_lodging_common_cot",
                        "service_kind": "lodging",
                        "label": "Common room cot",
                        "price": {"gold": 0, "silver": 5, "copper": 0},
                    },
                    {
                        "offer_id": "bran_lodging_private_room",
                        "service_kind": "lodging",
                        "label": "Private room",
                        "price": {"gold": 1, "silver": 0, "copper": 0},
                    },
                ],
                "selected_offer_id": "",
                "purchase": None,
                "available_actions": [],
                "source": "deterministic_service_resolver",
            },
            "narration_brief": {
                "summary": "I ask Bran for a room to rent",
            },
            "resolved_result": {
                "service_result": {
                    "matched": True,
                    "kind": "service_inquiry",
                    "service_kind": "lodging",
                    "provider_id": "npc:Bran",
                    "provider_name": "Bran",
                    "location_id": "loc_tavern",
                    "status": "offers_available",
                    "offers": [
                        {
                            "offer_id": "bran_lodging_common_cot",
                            "service_kind": "lodging",
                            "label": "Common room cot",
                            "price": {"gold": 0, "silver": 5, "copper": 0},
                        },
                        {
                            "offer_id": "bran_lodging_private_room",
                            "service_kind": "lodging",
                            "label": "Private room",
                            "price": {"gold": 1, "silver": 0, "copper": 0},
                        },
                    ],
                    "selected_offer_id": "",
                    "purchase": None,
                    "available_actions": [],
                    "source": "deterministic_service_resolver",
                }
            },
        },
        "resolved_result": {
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "lodging",
                "provider_id": "npc:Bran",
                "provider_name": "Bran",
                "location_id": "loc_tavern",
                "status": "offers_available",
                "offers": [
                    {
                        "offer_id": "bran_lodging_common_cot",
                        "service_kind": "lodging",
                        "label": "Common room cot",
                        "price": {"gold": 0, "silver": 5, "copper": 0},
                    },
                    {
                        "offer_id": "bran_lodging_private_room",
                        "service_kind": "lodging",
                        "label": "Private room",
                        "price": {"gold": 1, "silver": 0, "copper": 0},
                    },
                ],
                "selected_offer_id": "",
                "purchase": None,
                "available_actions": [],
                "source": "deterministic_service_resolver",
            }
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran checks the available options." in text

    assert "i have a few" not in text
    assert "not cheap" not in text

    assert "common room cot for 5 silver" in text
    assert "private room for 1 gold" in text
    assert narration_json["action"] == "Bran checks the available options."
    assert narration_json["npc"]["line"] == (
        "I can offer Common room cot for 5 silver or Private room for 1 gold."
    )
