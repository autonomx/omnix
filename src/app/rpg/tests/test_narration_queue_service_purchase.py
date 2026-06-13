"""Tests for narration job queue functionality."""




def test_service_narration_ignores_registered_resolved_message_for_inquiry_action():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara reviews the repair request.",'
                    '"action":"The inquiry is successfully registered by Elara; she confirms that basic repair services are available for purchase from her stall.",'
                    '"npc":{"speaker":"Elara","line":"I can offer Basic gear repair for 4 silver."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_inquiry",
        "service_kind": "repair",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "offers_available",
        "offers": [
            {
                "offer_id": "elara_basic_repair",
                "service_kind": "repair",
                "label": "Basic gear repair",
                "price": {"gold": 0, "silver": 4, "copper": 0},
            }
        ],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I ask Elara to repair my gear",
            "turn_contract": {
                "player_input": "I ask Elara to repair my gear",
                "service_result": service_result,
                "resolved_result": {
                    "service_result": service_result,
                    "message": "The inquiry is successfully registered by Elara; she confirms that basic repair services are available for purchase from her stall.",
                },
                "narration_brief": {"summary": "I ask Elara to repair my gear"},
            },
            "resolved_result": {
                "service_result": service_result,
                "message": "The inquiry is successfully registered by Elara; she confirms that basic repair services are available for purchase from her stall.",
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert result["narration_json"]["action"] == "Elara checks the available options."
    assert "registered" not in result["narration"].lower()

def test_service_narration_paragraph_does_not_repeat_player_input():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"As you ask Bran about a room to rent, the tavern grows quiet.",'
                    '"action":"You ask Bran for a room to rent.",'
                    '"npc":{"speaker":"Bran","line":"I have a few rooms."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
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
            }
        ],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I ask Bran for a room to rent",
            "turn_contract": {
                "player_input": "I ask Bran for a room to rent",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I ask Bran for a room to rent"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "as you ask" not in text
    assert "about a room to rent" not in text
    assert narration_json["narration"] == "Bran looks over the available lodging options."

def test_service_narration_uses_registered_shop_offers():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara folds her hands over the counter.",'
                    '"action":"You ask Elara what she sells.",'
                    '"npc":{"speaker":"Elara","line":"I have all sorts of goods for sale."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_inquiry",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "offers_available",
        "offers": [
            {
                "offer_id": "elara_torch",
                "service_kind": "shop_goods",
                "label": "Torch",
                "price": {"gold": 0, "silver": 1, "copper": 0},
            },
            {
                "offer_id": "elara_rope",
                "service_kind": "shop_goods",
                "label": "Rope",
                "price": {"gold": 0, "silver": 3, "copper": 0},
            },
        ],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Central Market", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I ask Elara what she sells",
            "turn_contract": {
                "player_input": "I ask Elara what she sells",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I ask Elara what she sells"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()

    assert "result: elara checks the available options." in text
    assert "all sorts of goods" not in text
    assert "torch for 1 silver" in text
    assert "rope for 3 silver" in text

def test_service_purchase_applied_narration_reports_completed_purchase():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara reaches below the counter.",'
                    '"action":"You buy a torch from Elara.",'
                    '"npc":{"speaker":"Elara","line":"The torch is yours."},'
                    '"reward":"Torch","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "purchased",
        "offers": [
            {
                "offer_id": "elara_torch",
                "service_kind": "shop_goods",
                "label": "Torch",
                "price": {"gold": 0, "silver": 1, "copper": 0},
            }
        ],
        "selected_offer_id": "elara_torch",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 1, "copper": 0},
            "can_afford": True,
            "applied": True,
            "resource_changes": {"currency": {"gold": 0, "silver": -1, "copper": 0}},
            "effects": {"items_added": [{"item_id": "torch", "name": "Torch", "quantity": 1}]},
            "applied_effects": {
                "currency_changed": True,
                "items_added": [{"item_id": "torch", "name": "Torch", "quantity": 1}],
                "active_service": {},
                "rumor_added": {},
            },
            "note": "Purchase intent resolved deterministically; runtime applies mutation.",
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Central Market", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy a torch from Elara",
            "turn_contract": {
                "player_input": "I buy a torch from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I buy a torch from Elara"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "elara reaches below the counter" in text
    assert "you buy a torch from elara" in text
    assert "the torch is yours" in text
    assert "done. torch is settled" not in text
    assert "reward:" not in text
    assert narration_json["reward"] == ""


def test_service_purchase_applied_narration_grounds_conflicting_offer_claim():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran marks the room ledger.",'
                    '"action":"You buy a private room from Bran.",'
                    '"npc":{"speaker":"Bran","line":"Done. Private room is settled."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "lodging",
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "location_id": "loc_tavern",
        "status": "purchased",
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
        "selected_offer_id": "bran_lodging_common_cot",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "can_afford": True,
            "applied": True,
            "resource_changes": {"currency": {"gold": 0, "silver": -5, "copper": 0}},
            "effects": {"lodging_reserved": True},
            "applied_effects": {
                "currency_changed": True,
                "items_added": [],
                "active_service": {"offer_id": "bran_lodging_common_cot"},
                "rumor_added": {},
            },
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I buy Common room cot from Bran",
            "turn_contract": {
                "player_input": "I buy Common room cot from Bran",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I buy Common room cot from Bran"},
            },
            "resolved_result": {"service_result": service_result},
            "service_application": {"applied": True},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()

    assert "private room is settled" not in text
    assert "done. common room cot is settled" in text

def test_service_purchase_blocked_narration_reports_insufficient_funds():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara hands you the rope.",'
                    '"action":"You buy rope from Elara.",'
                    '"npc":{"speaker":"Elara","line":"The rope is yours."},'
                    '"reward":"Rope","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "blocked",
        "offers": [
            {
                "offer_id": "elara_rope",
                "service_kind": "shop_goods",
                "label": "Rope",
                "price": {"gold": 0, "silver": 3, "copper": 0},
            }
        ],
        "selected_offer_id": "elara_rope",
        "purchase": {
            "blocked": True,
            "blocked_reason": "insufficient_funds",
            "price": {"gold": 0, "silver": 3, "copper": 0},
            "can_afford": False,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": 0, "copper": 0}},
            "effects": {},
            "note": "No mutation was applied.",
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Central Market", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy rope from Elara",
            "turn_contract": {
                "player_input": "I buy rope from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I buy rope from Elara"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "hands you the rope" not in text
    assert "the rope is yours" not in text
    assert "reward:" not in text
    assert "result: elara names the price, but you do not have enough coin." in text
    assert "rope for 3 silver is the price, but you do not have enough coin." in text
    assert narration_json["reward"] == ""

def test_service_purchase_narration_prefers_resolved_applied_result():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran reaches for the ledger.",'
                    '"action":"You buy Common room cot from Bran.",'
                    '"npc":{"speaker":"Bran","line":"I can settle Common room cot once you confirm the purchase."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    stale_service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "lodging",
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "location_id": "loc_tavern",
        "status": "purchase_ready",
        "offers": [
            {
                "offer_id": "bran_lodging_common_cot",
                "service_kind": "lodging",
                "label": "Common room cot",
                "price": {"gold": 0, "silver": 5, "copper": 0},
            }
        ],
        "selected_offer_id": "bran_lodging_common_cot",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "can_afford": True,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": -5, "copper": 0}},
            "effects": {"lodging_reserved": True, "rest_quality": "basic", "duration": "one_night"},
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    applied_service_result = {
        **stale_service_result,
        "status": "purchased",
        "purchase": {
            **stale_service_result["purchase"],
            "applied": True,
            "applied_effects": {
                "currency_changed": True,
                "items_added": [],
                "active_service": {
                    "service_id": "bran_lodging_common_cot",
                    "offer_id": "bran_lodging_common_cot",
                    "service_kind": "lodging",
                    "provider_id": "npc:Bran",
                    "provider_name": "Bran",
                    "label": "Common room cot",
                    "started_tick": 12,
                    "duration": "one_night",
                    "status": "active",
                },
                "rumor_added": {},
            },
        },
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I buy Common room cot from Bran",
            "turn_contract": {
                "player_input": "I buy Common room cot from Bran",
                "service_result": stale_service_result,
                "resolved_result": {
                    "service_result": applied_service_result,
                    "service_application": {"applied": True},
                },
            },
            "resolved_result": {
                "service_result": applied_service_result,
                "service_application": {"applied": True},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "once you confirm" not in text
    assert "action: you buy common room cot from bran" in text
    assert "done. common room cot is settled." in text
    assert narration_json["action"] == "You buy Common room cot from Bran"
    assert narration_json["npc"]["line"] == "Done. Common room cot is settled."

def test_service_purchase_offer_not_found_narration_does_not_invent_item_details():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara gestures toward a fine sword displayed among her wares.",'
                    '"action":"Elara considers the sword purchase.",'
                    '"npc":{"speaker":"Elara","line":"That sword requires more than good intentions."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "purchase_offer_not_found",
        "offers": [
            {
                "offer_id": "elara_torch",
                "service_kind": "shop_goods",
                "label": "Torch",
                "price": {"gold": 0, "silver": 1, "copper": 0},
            },
            {
                "offer_id": "elara_rope",
                "service_kind": "shop_goods",
                "label": "Rope",
                "price": {"gold": 0, "silver": 3, "copper": 0},
            },
        ],
        "selected_offer_id": "",
        "purchase": {
            "blocked": True,
            "blocked_reason": "offer_not_found",
            "price": {"gold": 0, "silver": 0, "copper": 0},
            "can_afford": False,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": 0, "copper": 0}},
            "effects": {},
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I try to buy a sword I cannot afford",
            "turn_contract": {
                "player_input": "I try to buy a sword I cannot afford",
                "service_result": service_result,
                "resolved_result": {
                    "service_result": service_result,
                    "service_application": {
                        "applied": False,
                        "blocked": True,
                        "blocked_reason": "offer_not_found",
                    },
                },
            },
            "resolved_result": {
                "service_result": service_result,
                "service_application": {
                    "applied": False,
                    "blocked": True,
                    "blocked_reason": "offer_not_found",
                },
            },
            "service_result": service_result,
            "service_application": {
                "applied": False,
                "blocked": True,
                "blocked_reason": "offer_not_found",
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "fine sword" not in text
    assert "displayed among her wares" not in text
    assert "good intentions" not in text
    assert narration_json["action"] == "Elara cannot find a matching available offer."
    assert narration_json["npc"]["line"] == "I do not have that listed among my available offers."

def test_service_purchase_narration_uses_direct_service_application_when_contract_is_stale():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran waits with the ledger open.",'
                    '"action":"Bran is ready to complete the purchase.",'
                    '"npc":{"speaker":"Bran","line":"I can settle Common room cot once you confirm the purchase."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    stale_service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "lodging",
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "location_id": "loc_tavern",
        "status": "purchase_ready",
        "offers": [
            {
                "offer_id": "bran_lodging_common_cot",
                "service_kind": "lodging",
                "label": "Common room cot",
                "price": {"gold": 0, "silver": 5, "copper": 0},
            }
        ],
        "selected_offer_id": "bran_lodging_common_cot",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "can_afford": True,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": -5, "copper": 0}},
            "effects": {"lodging_reserved": True, "rest_quality": "basic", "duration": "one_night"},
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I buy Common room cot from Bran",
            "turn_contract": {
                "player_input": "I buy Common room cot from Bran",
                "service_result": stale_service_result,
                "resolved_result": {
                    "service_result": stale_service_result,
                    "service_application": {"applied": False},
                },
            },
            # This is what runtime should now pass directly after mutation.
            "resolved_result": {
                "service_result": {
                    **stale_service_result,
                    "status": "purchased",
                    "purchase": {
                        **stale_service_result["purchase"],
                        "applied": True,
                    },
                },
                "service_application": {"applied": True},
            },
            "service_result": {
                **stale_service_result,
                "status": "purchased",
                "purchase": {
                    **stale_service_result["purchase"],
                    "applied": True,
                },
            },
            "service_application": {"applied": True},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "ready to complete" not in text
    assert "once you confirm" not in text
    assert "action: you buy common room cot from bran" in text
    assert "done. common room cot is settled." in text
    assert narration_json["action"] == "You buy Common room cot from Bran"
    assert narration_json["npc"]["line"] == "Done. Common room cot is settled."

def test_service_purchase_blocked_result_keeps_specific_grounded_reason_after_final_pass():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"The request to purchase a torch is processed by Elara.",'
                    '"action":"The attempt fails.",'
                    '"npc":{"speaker":"Elara","line":"Torch for 1 silver is the price, but you do not have enough coin."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "status": "blocked",
        "selected_offer_id": "elara_torch",
        "purchase": {
            "blocked": True,
            "blocked_reason": "insufficient_funds",
            "applied": False,
        },
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy a torch from Elara",
            "service_result": service_result,
            "service_application": {
                "blocked": True,
                "blocked_reason": "insufficient_funds",
            },
            "turn_contract": {
                "player_input": "I buy a torch from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert result["narration_json"]["action"] == (
        "Elara names the price, but you do not have enough coin."
    )
    assert "Result: Elara names the price, but you do not have enough coin." in result["narration"]
    assert "The attempt fails" not in result["narration"]
    assert "registered" not in result["narration"].lower()

def test_service_purchase_offer_not_found_result_keeps_specific_grounded_reason_after_final_pass():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara checks the registered offers.",'
                    '"action":"The attempt fails.",'
                    '"npc":{"speaker":"Elara","line":"I do not have that listed among my registered offers."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "status": "purchase_offer_not_found",
        "selected_offer_id": "",
        "purchase": {
            "blocked": True,
            "blocked_reason": "offer_not_found",
            "applied": False,
        },
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I try to buy a sword I cannot afford",
            "service_result": service_result,
            "service_application": {
                "blocked": True,
                "blocked_reason": "offer_not_found",
            },
            "turn_contract": {
                "player_input": "I try to buy a sword I cannot afford",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert result["narration_json"]["action"] == (
        "Elara cannot find a matching available offer."
    )
    assert "Result: Elara cannot find a matching available offer." in result["narration"]
    assert "The attempt fails" not in result["narration"]
    assert "registered" not in result["narration"].lower()
