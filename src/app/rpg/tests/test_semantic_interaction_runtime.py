from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.ai.semantic_action_intelligence import normalize_semantic_action_advisory
from app.rpg.session.public_state_bridge import (
    merge_authoritative_session_state,
    synchronize_player_projections,
)
from app.rpg.session.pending_interactions import (
    close_pending_service_offer,
    record_service_offer,
)
from app.rpg.session.semantic_interaction import (
    SEMANTIC_INTERACTION_VERSION,
    attach_semantic_interaction,
)
from app.rpg.session import interactive_first_call_runtime as interactive_runtime
from app.rpg.session import runtime_part39


def _session_with_public_wallet() -> dict:
    return {
        "state": {
            "player": {
                "currency": {"gold": 0, "silver": 10, "copper": 0},
                "inventory": [{"id": "torch", "name": "Torch", "quantity": 1}],
                "location_id": "loc_tavern",
            }
        },
        "simulation_state": {},
        "runtime_state": {},
    }


def test_public_player_wallet_hydrates_authoritative_simulation() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())

    player = session["simulation_state"]["player_state"]
    assert player["currency"] == {"gold": 0, "silver": 10, "copper": 0}
    assert player["inventory_state"]["currency"] == player["currency"]
    assert player["inventory_state"]["items"][0]["item_id"] == "torch"


def test_authoritative_wallet_projects_back_to_public_state() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())
    session["simulation_state"]["player_state"]["currency"] = {
        "gold": 0,
        "silver": 8,
        "copper": 5,
    }
    session["simulation_state"]["player_state"]["inventory_state"]["currency"] = {
        "gold": 0,
        "silver": 8,
        "copper": 5,
    }

    projected = synchronize_player_projections(session)

    assert projected["state"]["player"]["currency"] == {
        "gold": 0,
        "silver": 8,
        "copper": 5,
    }


def test_authoritative_simulation_survives_stale_presentation_session_merge() -> None:
    stale = synchronize_player_projections(_session_with_public_wallet())
    authoritative = {
        "simulation_state": {
            **stale["simulation_state"],
            "player_state": {
                **stale["simulation_state"]["player_state"],
                "currency": {"gold": 0, "silver": 5, "copper": 0},
                "inventory_state": {
                    **stale["simulation_state"]["player_state"]["inventory_state"],
                    "currency": {"gold": 0, "silver": 5, "copper": 0},
                },
            },
            "active_services": [{"service_id": "bran_lodging_common_cot", "status": "active"}],
        }
    }

    merged = merge_authoritative_session_state(stale, authoritative)

    assert merged["state"]["player"]["currency"] == {
        "gold": 0,
        "silver": 5,
        "copper": 0,
    }
    assert merged["simulation_state"]["active_services"][0]["service_id"] == "bran_lodging_common_cot"


def test_llm_semantic_frame_resolves_registered_offer_without_phrase_rules() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())
    action = attach_semantic_interaction(
        {},
        {
            "action_type": "service_purchase",
            "semantic_family": "commerce",
            "target_id": "npc:Bran",
            "service_kind": "meal",
            "offer_id": "bran_meal_stew",
            "confidence": 0.93,
            "source": "test_llm_classifier",
        },
        player_input="Yes, that one please.",
    )

    result = resolve_service_turn(
        player_input="Yes, that one please.",
        action=action,
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    assert action["metadata"]["semantic_interaction"]["schema_version"] == SEMANTIC_INTERACTION_VERSION
    assert result["matched"] is True
    assert result["selected_offer_id"] == "bran_meal_stew"
    assert result["status"] == "purchase_ready"
    assert result["purchase"]["price"] == {"gold": 0, "silver": 1, "copper": 5}


def test_catalog_offer_alias_infers_service_kind_for_price_inquiry() -> None:
    result = resolve_service_turn(
        player_input="I ask Bran what an affordable common cot costs for one night.",
        action={},
        resolved_action={},
        simulation_state={},
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["kind"] == "service_inquiry"
    assert result["service_kind"] == "lodging"
    assert {offer["offer_id"] for offer in result["offers"]} == {
        "bran_lodging_common_cot",
        "bran_lodging_private_room",
    }


def test_map_location_alias_allows_canonical_provider_transaction() -> None:
    result = resolve_service_turn(
        player_input="I buy the common room cot from Bran for one night and pay 5 silver.",
        action={},
        resolved_action={},
        simulation_state={
            "player_state": {
                "location_id": "rusty_flagon_tavern",
                "currency": {"gold": 0, "silver": 10, "copper": 0},
            }
        },
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["status"] == "purchase_ready"
    assert result["selected_offer_id"] == "bran_lodging_common_cot"


def test_outer_authoritative_boundary_reapplies_service_guard(monkeypatch) -> None:
    session = _session_with_public_wallet()
    session["simulation_state"] = {
        "player_state": {"location_id": "rusty_flagon_tavern"}
    }
    monkeypatch.setattr(runtime_part39, "load_runtime_session", lambda _session_id: session)
    saved = {}
    monkeypatch.setattr(
        runtime_part39,
        "save_runtime_session",
        lambda value: saved.update(value) or value,
    )

    captured = {}

    def fake_authoritative(session_id, player_input, action, *, performance_override=None):
        captured.update({"session_id": session_id, "player_input": player_input, "action": action})
        return {
            "ok": True,
            "result": {"service_application": {"applied": True}},
        }

    result = runtime_part39._apply_turn_authoritative(
        "guarded-service-test",
        "I buy the common room cot from Bran for one night and pay 5 silver.",
        {},
        _base_authoritative=fake_authoritative,
    )

    assert result["ok"] is True
    assert captured["action"]["action_type"] == "service_purchase"
    assert captured["action"]["metadata"]["service_result"]["selected_offer_id"] == "bran_lodging_common_cot"
    assert saved["state"]["player"]["currency"] == {
        "gold": 0,
        "silver": 5,
        "copper": 0,
    }
    assert saved["simulation_state"]["active_services"][0]["service_id"] == "bran_lodging_common_cot"
    assert result["deterministic_fallback_narration"] == (
        "You pay 5 silver to Bran for Common room cot. The transaction is complete."
    )


def test_structured_private_room_purchase_uses_cross_denomination_value() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())
    action = attach_semantic_interaction(
        {},
        {
            "action_type": "service_purchase",
            "target_id": "npc:Bran",
            "service_kind": "lodging",
            "offer_id": "bran_lodging_private_room",
            "confidence": 0.98,
        },
        player_input="The private option, please.",
    )

    result = resolve_service_turn(
        player_input="The private option, please.",
        action=action,
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={},
    )

    assert result["status"] == "purchase_ready"
    assert result["purchase"]["can_afford"] is True
    assert result["purchase"]["price"] == {"gold": 1, "silver": 0, "copper": 0}


def test_single_pending_offer_resolves_confirmation_without_phrase_aliases() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())
    inquiry = resolve_service_turn(
        player_input="What does the stew cost?",
        action={},
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={},
    )
    pending = record_service_offer(session["simulation_state"], inquiry, tick=3)

    result = resolve_service_turn(
        player_input="Sounds good, yes.",
        action=attach_semantic_interaction(
            {},
            {
                "action_type": "service_purchase",
                "target_id": "npc:Bran",
                "service_kind": "meal",
                "confirmation": True,
            },
            player_input="Sounds good, yes.",
        ),
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={"tick": 4},
    )

    assert pending["candidate_ids"] == ["bran_meal_stew"]
    assert result["selected_offer_id"] == "bran_meal_stew"
    assert result["status"] == "purchase_ready"


def test_multiple_pending_offers_require_specific_selection() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())
    inquiry = resolve_service_turn(
        player_input="What food does Bran have?",
        action={},
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={},
    )
    pending = record_service_offer(session["simulation_state"], inquiry, tick=3)

    result = resolve_service_turn(
        player_input="Yes, I'll take it.",
        action=attach_semantic_interaction(
            {},
            {
                "action_type": "service_purchase",
                "target_id": "npc:Bran",
                "service_kind": "meal",
                "confirmation": True,
            },
            player_input="Yes, I'll take it.",
        ),
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={"tick": 4},
    )

    assert len(pending["candidate_ids"]) == 2
    assert result["status"] == "purchase_offer_not_found"


def test_resolved_pending_offer_is_closed_idempotently() -> None:
    session = synchronize_player_projections(_session_with_public_wallet())
    inquiry = resolve_service_turn(
        player_input="What does the stew cost?",
        action={},
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={},
    )
    record_service_offer(session["simulation_state"], inquiry, tick=3)

    closed = close_pending_service_offer(
        session["simulation_state"],
        provider_id="npc:Bran",
        service_kind="meal",
        selected_offer_id="bran_meal_stew",
        tick=4,
    )
    closed_again = close_pending_service_offer(
        session["simulation_state"],
        provider_id="npc:Bran",
        service_kind="meal",
        selected_offer_id="bran_meal_stew",
        tick=5,
    )

    assert closed["status"] == "resolved"
    assert closed["resolved_offer_id"] == "bran_meal_stew"
    assert closed_again == {}


def test_llm_router_preserves_generic_service_entities_for_runtime_validation() -> None:
    advisory = normalize_semantic_action_advisory(
        {
            "action_intent": {
                "action_type": "service_purchase",
                "target_id": "npc:generated_innkeeper",
                "target_name": "Mara",
                "service_kind": "lodging",
                "offer_id": "mara_room_2",
                "confirmation": True,
                "duration_policy": "until next morning",
                "confidence": 0.91,
                "ambiguities": [],
                "stateful": True,
                "needs_runtime_resolution": True,
            },
            "semantic_advisory": {
                "semantic_family": "commerce",
                "risk_domain": "commerce",
                "state_mutation_requested": True,
            },
            "dialogue_gate": {"safe_to_display_now": False, "reason": "stateful", "risk_flags": ["commerce"]},
            "final_narration_candidate": {},
        },
        {},
    )

    assert advisory["action_type"] == "service_purchase"
    assert advisory["semantic_family"] == "commerce"
    assert advisory["service_kind"] == "lodging"
    assert advisory["offer_id"] == "mara_room_2"
    assert advisory["confirmation"] is True
    assert advisory["duration_policy"] == "until_next_morning"
    assert advisory["confidence"] == 0.91


def test_interactive_wrapper_forwards_matched_service_as_stateful_action(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime, "_prepare_stateful_runtime_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        interactive_runtime,
        "_apply_stateful_narration_contract",
        lambda result, **kwargs: result,
    )

    def fake_apply_turn(*, session_id, player_input, action, performance_override):
        captured.update(
            {
                "session_id": session_id,
                "player_input": player_input,
                "action": action,
                "performance_override": performance_override,
            }
        )
        return {"ok": True, "result": {"ok": True}}

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fake_apply_turn)

    result = interactive_runtime.apply_turn(
        "semantic-service-test",
        "I buy one hot stew from Bran.",
        session_override=_session_with_public_wallet(),
    )

    assert result["ok"] is True
    assert captured["action"]["action_type"] == "service_purchase"
    assert captured["action"]["service_kind"] == "meal"
    assert captured["action"]["metadata"]["service_result"]["selected_offer_id"] == "bran_meal_stew"
