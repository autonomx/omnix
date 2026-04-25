from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.rpg.session.runtime import apply_turn

OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "test-results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "manual_rpg_llm_transcript.txt"

_OUTPUT_LINES: List[str] = []


def _emit(value: Any = "") -> None:
    text = "" if value is None else str(value)
    print(text)
    _OUTPUT_LINES.append(text)


def _reset_output() -> None:
    _OUTPUT_LINES.clear()


def _write_output(path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(_OUTPUT_LINES) + "\n", encoding="utf-8")
    print(f"Wrote transcript to: {path.resolve()}")


MANUAL_TEST_TURNS = [
    "I ask Bran for a room to rent",
    "I ask Bran for food",
    "I ask Bran if he has heard any rumors",
    "I ask Elara what she sells",
    "I buy a torch from Elara",
    "I try to buy a sword I cannot afford",
    "I ask Elara to repair my gear",
    "I ask Bran for directions to the market",
]

SERVICE_SCENARIOS = {
    "lodging_success": {
        "currency": {"gold": 0, "silver": 5, "copper": 0},
        "turns": [
            "I ask Bran for a room to rent",
            "I buy Common room cot from Bran",
        ],
    },
    "shop_success": {
        "currency": {"gold": 0, "silver": 2, "copper": 0},
        "turns": [
            "I ask Elara what she sells",
            "I buy a torch from Elara",
        ],
    },
    "blocked_purchase": {
        "currency": {"gold": 0, "silver": 1, "copper": 0},
        "turns": [
            "I ask Elara what she sells",
            "I buy rope from Elara",
        ],
    },
    "paid_info": {
        "currency": {"gold": 0, "silver": 2, "copper": 0},
        "turns": [
            "I ask Bran if he has heard any rumors",
            "I buy Local rumor from Bran",
        ],
    },
}

PROMPTS = MANUAL_TEST_TURNS

LEGACY_PROMPTS = [
    "I ask Bran for a room to rent",
    "I want a better room. I then punch Bran",
    "I throw Bran to the ground",
    "I then apologize to Bran",
    "I ask Bran how he feels",
    "I ask Bran if he still has a room available",
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clone_or_create_manual_session(session_id: str) -> Dict[str, Any]:
    """
    Manual scenario sessions need to exist before apply_turn(...).

    apply_turn does not create arbitrary session IDs, so clone the known
    manual_test_session shape when available. If the session service exposes
    save/load helpers, persist the clone before running scenario turns.
    """
    try:
        from app.rpg.session.service import load_session, save_session

        existing = load_session(session_id)
        if existing:
            return _safe_dict(existing)

        template = load_session("manual_test_session")
        if template:
            cloned = deepcopy(template)
            manifest = _safe_dict(cloned.get("manifest"))
            manifest["session_id"] = session_id
            manifest["id"] = f"session:{session_id}"
            manifest["title"] = f"Manual Service Scenario: {session_id}"
            cloned["manifest"] = manifest

            runtime_state = _safe_dict(cloned.get("runtime_state"))
            runtime_state["tick"] = 0
            runtime_state["turn_history"] = []
            runtime_state["last_turn_contract"] = {}
            runtime_state["last_turn_result"] = {}
            cloned["runtime_state"] = runtime_state

            save_session(cloned)
            return cloned
    except Exception:
        pass

    return {}


def _ensure_manual_session(session_id: str) -> Dict[str, Any]:
    session = _clone_or_create_manual_session(session_id)
    if session:
        return session

    warmup = apply_turn(session_id="manual_test_session", player_input="I wait")
    template_session = _extract_session(warmup)
    if not template_session:
        return {}

    try:
        from app.rpg.session.service import save_session

        cloned = deepcopy(template_session)
        manifest = _safe_dict(cloned.get("manifest"))
        manifest["session_id"] = session_id
        manifest["id"] = f"session:{session_id}"
        manifest["title"] = f"Manual Service Scenario: {session_id}"
        cloned["manifest"] = manifest
        save_session(cloned)
        return cloned
    except Exception:
        return {}


def _extract_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    return _safe_dict(result.get("result") or result)


def _extract_session(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(result).get("session"))


def _extract_simulation_state(result: Dict[str, Any]) -> Dict[str, Any]:
    session = _extract_session(result)
    direct = _safe_dict(session.get("simulation_state"))
    if direct:
        return direct

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    return _safe_dict(metadata.get("simulation_state"))


def _extract_player_inventory(result: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result)
    player_state = _safe_dict(simulation_state.get("player_state"))
    return _safe_dict(player_state.get("inventory_state"))


def _extract_player_currency(result: Dict[str, Any]) -> Dict[str, Any]:
    inventory_state = _extract_player_inventory(result)
    return _safe_dict(inventory_state.get("currency"))


def _extract_player_items(result: Dict[str, Any]) -> List[Any]:
    inventory_state = _extract_player_inventory(result)
    return _safe_list(inventory_state.get("items"))


def _extract_active_services(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    return _safe_list(simulation_state.get("active_services"))


def _extract_memory_rumors(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    return _safe_list(memory_state.get("rumors"))


def _extract_transaction_history(result: Dict[str, Any]) -> List[Any]:
    simulation_state = _extract_simulation_state(result)
    return _safe_list(simulation_state.get("transaction_history"))


def _seed_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        return False

    simulation_state = _extract_simulation_state({"session": session})
    if not simulation_state:
        setup_payload = _safe_dict(session.get("setup_payload"))
        metadata = _safe_dict(setup_payload.get("metadata"))
        simulation_state = _safe_dict(metadata.get("simulation_state"))
        if not simulation_state:
            simulation_state = {}
            metadata["simulation_state"] = simulation_state

    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {"items": [], "equipment": {}, "capacity": 50, "last_loot": []}
        player_state["inventory_state"] = inventory_state

    inventory_state["currency"] = {
        "gold": int(currency.get("gold") or 0),
        "silver": int(currency.get("silver") or 0),
        "copper": int(currency.get("copper") or 0),
    }

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    if metadata is not setup_payload.get("metadata"):
        setup_payload["metadata"] = metadata
    metadata["simulation_state"] = simulation_state

    try:
        from app.rpg.session.service import save_session
        save_session(session)
    except Exception:
        return False

    return True


def _write_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    try:
        from app.rpg.session.service import load_session, save_session
    except Exception:
        return False

    session = load_session(session_id)
    if not session:
        return False

    simulation_state = _extract_simulation_state({"session": session})
    if not simulation_state:
        setup_payload = _safe_dict(session.get("setup_payload"))
        metadata = _safe_dict(setup_payload.get("metadata"))
        simulation_state = _safe_dict(metadata.get("simulation_state"))
        if not simulation_state:
            simulation_state = {}
            metadata["simulation_state"] = simulation_state
        setup_payload["metadata"] = metadata
        session["setup_payload"] = setup_payload

    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {
            "items": [],
            "equipment": {},
            "capacity": 50,
            "last_loot": [],
        }
        player_state["inventory_state"] = inventory_state

    inventory_state["currency"] = {
        "gold": int(currency.get("gold") or 0),
        "silver": int(currency.get("silver") or 0),
        "copper": int(currency.get("copper") or 0),
    }

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload

    try:
        save_session(session)
        return True
    except Exception:
        return False


def _extract_narration(result: Dict[str, Any]) -> str:
    # Check direct keys
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in result subdict
    result_sub = _safe_dict(result.get("result"))
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result_sub.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in session runtime_state
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    for key in ("last_narration", "last_turn_narration"):
        value = runtime_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check authoritative
    authoritative = _safe_dict(result.get("authoritative"))
    for key in ("summary", "deterministic_fallback_narration"):
        value = authoritative.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _compact_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _extract_turn_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    payload = _safe_dict(result.get("result") or result)
    contract = _safe_dict(payload.get("turn_contract"))
    if contract:
        return contract

    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    return _safe_dict(runtime_state.get("last_turn_contract"))


def _extract_service_debug(result: Dict[str, Any]) -> Dict[str, Any]:
    contract = _extract_turn_contract(result)
    contract_service_result = _safe_dict(contract.get("service_result"))
    resolved = _safe_dict(contract.get("resolved_result") or contract.get("resolved_action"))
    resolved_service_result = _safe_dict(resolved.get("service_result"))
    presentation = _safe_dict(contract.get("presentation"))

    service = resolved_service_result or contract_service_result
    purchase = _safe_dict(service.get("purchase"))
    resource_changes = _safe_dict(purchase.get("resource_changes"))
    applied_effects = _safe_dict(purchase.get("applied_effects"))
    effects = _safe_dict(purchase.get("effects"))
    service_application = _safe_dict(resolved.get("service_application"))

    return {
        "service_result": service,
        "available_actions": _safe_list(
            presentation.get("available_actions") or service.get("available_actions")
        ),
        "resource_changes": resource_changes,
        "purchase": purchase,
        "service_application": service_application,
        "transaction_record": _safe_dict(
            resolved.get("transaction_record")
            or service_application.get("transaction_record")
        ),
        "inventory_changes": {
            "items_added": _safe_list(
                applied_effects.get("items_added") or effects.get("items_added")
            ),
            "items_removed": _safe_list(
                applied_effects.get("items_removed") or effects.get("items_removed")
            ),
        },
    }


def _effective_player_currency_after(result: Dict[str, Any]) -> Dict[str, Any]:
    service_debug = _extract_service_debug(result)
    service_application = _safe_dict(service_debug.get("service_application"))
    if service_application.get("currency_after"):
        return _safe_dict(service_application.get("currency_after"))

    service_result = _safe_dict(service_debug.get("service_result"))
    if service_result.get("player_currency"):
        return _safe_dict(service_result.get("player_currency"))

    return _extract_player_currency(result)


def _print_turn(
    index: int,
    player_input: str,
    result: Dict[str, Any],
    before_currency: Dict[str, Any] | None = None,
    before_items: List[Any] | None = None,
) -> None:
    result_sub = _safe_dict(result.get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narrative"))
    narration_json = _safe_dict(raw_payload.get("narration_json"))
    raw_llm_text = raw_payload.get("raw_llm_narrative")
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    narration = _extract_narration(result)
    turn_contract = _extract_turn_contract(result)
    service_debug = _extract_service_debug(result)

    _emit("=" * 80)
    _emit(f"TURN {index}")
    _emit(f"PLAYER: {player_input}")
    _emit("")

    if result.get("error"):
        _emit("ERROR:")
        _emit(result["error"])
        _emit("")
        _emit("TRACEBACK:")
        _emit(result.get("traceback", "")[:2000])
        _emit("")

    _emit("NARRATION:")
    _emit(narration or "[no narration found]")
    _emit("")
    _emit("TURN CONTRACT:")
    _emit(_compact_json(turn_contract))
    _emit("")
    _emit("SERVICE RESULT:")
    _emit(_compact_json(service_debug.get("service_result")))
    _emit("")
    _emit("AVAILABLE ACTIONS:")
    _emit(_compact_json(service_debug.get("available_actions")))
    _emit("")
    _emit("RESOURCE CHANGES:")
    _emit(_compact_json(service_debug.get("resource_changes")))
    _emit("")
    _emit("INVENTORY CHANGES:")
    _emit(_compact_json(service_debug.get("inventory_changes")))
    _emit("")
    _emit("PLAYER CURRENCY BEFORE:")
    _emit(_compact_json(before_currency or {}))
    _emit("")
    _emit("PLAYER CURRENCY AFTER:")
    _emit(_compact_json(_effective_player_currency_after(result)))
    _emit("")
    _emit("PLAYER ITEMS BEFORE:")
    _emit(_compact_json(before_items or []))
    _emit("")
    _emit("PLAYER ITEMS AFTER:")
    _emit(_compact_json(_extract_player_items(result)))
    _emit("")
    _emit("ACTIVE SERVICES:")
    _emit(_compact_json(_extract_active_services(result)))
    _emit("")
    _emit("MEMORY RUMORS:")
    _emit(_compact_json(_extract_memory_rumors(result)))
    _emit("")
    _emit("TRANSACTION RECORD:")
    _emit(_compact_json(service_debug.get("transaction_record")))
    _emit("")
    _emit("TRANSACTION HISTORY:")
    _emit(_compact_json(_extract_transaction_history(result)))
    _emit("")
    _emit("RESULT SUBDICT:")
    _emit(_compact_json(result_sub))
    _emit("")
    _emit("NARRATION DEBUG:")
    _emit(_compact_json({
        "final_narration": result_sub.get("narration"),
        "used_llm": result_sub.get("used_llm"),
        "narration_status": result_sub.get("narration_status"),
        "raw_llm_text": raw_llm_text,
        "raw_payload_narration": raw_payload.get("narration"),
        "narration_json": narration_json,
        "json_narration": narration_json.get("narration"),
        "json_action": narration_json.get("action"),
        "json_npc": narration_json.get("npc"),
        "turn_contract_action": _safe_dict(turn_contract.get("action")),
        "turn_contract_resolved": _safe_dict(turn_contract.get("resolved_result")),
    }))
    _emit("")
    _emit("RUNTIME STATE KEYS:")
    _emit(", ".join(sorted(runtime_state.keys())))
    _emit("")
    _emit("RAW RESULT:")
    _emit(_compact_json(result))
    _emit("")


def run_manual_transcript(turns: List[str], session_id: str = "manual_test_session") -> None:
    _reset_output()
    _emit("Manual RPG LLM Transcript")
    _emit("")
    _emit(f"session_id: {session_id}")

    for index, player_input in enumerate(turns, start=1):
        before_result = apply_turn(session_id=session_id, player_input="I wait")
        before_currency = _extract_player_currency(before_result)
        before_items = _extract_player_items(before_result)
        result = apply_turn(session_id=session_id, player_input=player_input)
        _print_turn(index, player_input, result, before_currency, before_items)

    _write_output(OUTPUT_PATH)


def run_service_scenarios(selected: str = "all") -> None:
    _reset_output()

    if selected == "all":
        scenario_items = list(SERVICE_SCENARIOS.items())
    else:
        scenario_items = [(selected, SERVICE_SCENARIOS[selected])]

    _emit("Manual RPG Service Scenario Transcript")
    _emit("")
    _emit(f"scenario_filter: {selected}")
    _emit(f"scenario_count: {len(scenario_items)}")
    _emit("")

    scenario_summaries: List[Dict[str, Any]] = []

    for scenario_name, scenario in scenario_items:
        session_id = f"manual_service_{scenario_name}"
        currency = _safe_dict(scenario.get("currency"))
        turns = _safe_list(scenario.get("turns"))

        _emit("")
        _emit("#" * 80)
        _emit(f"SCENARIO: {scenario_name}")
        _emit(f"session_id: {session_id}")
        _emit("SEEDED CURRENCY:")
        _emit(_compact_json(currency))
        _emit("#" * 80)

        seeded = _seed_session_currency(session_id, currency)
        if not seeded:
            _emit("ERROR:")
            _emit(f"Could not create or seed scenario session: {session_id}")
            _emit("Make sure manual_test_session exists, or update _ensure_manual_session to use your session creation API.")
            _emit("")
            scenario_summaries.append(
                {
                    "scenario": scenario_name,
                    "session_id": session_id,
                    "seeded_currency": currency,
                    "error": "scenario_session_seed_failed",
                    "turns": [],
                }
            )
            continue

        last_result: Dict[str, Any] = {}
        scenario_results: List[Dict[str, Any]] = []
        current_currency = currency

        for index, player_input in enumerate(turns, start=1):
            if current_currency:
                _write_session_currency(session_id, current_currency)

            before_currency = current_currency or (
                _extract_player_currency(last_result) if last_result else currency
            )
            before_items = _extract_player_items(last_result) if last_result else []

            result = apply_turn(session_id=session_id, player_input=player_input)
            _print_turn(index, player_input, result, before_currency, before_items)

            service_debug = _extract_service_debug(result)
            service_result = _safe_dict(service_debug.get("service_result"))
            purchase = _safe_dict(service_debug.get("purchase"))
            service_application = _safe_dict(service_debug.get("service_application"))

            scenario_results.append(
                {
                    "turn": index,
                    "player_input": player_input,
                    "service_kind": service_result.get("service_kind"),
                    "kind": service_result.get("kind"),
                    "status": (
                        "purchased"
                        if service_application.get("applied")
                        else service_result.get("status")
                    ),
                    "selected_offer_id": service_result.get("selected_offer_id"),
                    "purchase_blocked": purchase.get("blocked"),
                    "purchase_applied": bool(
                        purchase.get("applied") or service_application.get("applied")
                    ),
                    "blocked_reason": purchase.get("blocked_reason"),
                    "currency_before": before_currency,
                    "currency_after": _effective_player_currency_after(result),
                    "items_after": _extract_player_items(result),
                    "active_services": _extract_active_services(result),
                    "memory_rumors": _extract_memory_rumors(result),
                    "transaction_record": service_debug.get("transaction_record"),
                    "transaction_history": _extract_transaction_history(result),
                    "service_application": service_application,
                }
            )

            next_currency = _effective_player_currency_after(result)
            if next_currency:
                current_currency = next_currency
            last_result = result

        scenario_summaries.append(
            {
                "scenario": scenario_name,
                "session_id": session_id,
                "seeded_currency": currency,
                "turns": scenario_results,
            }
        )

    _emit("")
    _emit("=" * 80)
    _emit("SCENARIO SUMMARY")
    _emit("=" * 80)
    _emit(_compact_json(scenario_summaries))

    suffix = selected if selected != "all" else "all"
    _write_output(OUTPUT_DIR / f"manual_rpg_service_scenarios_{suffix}.txt")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", default="manual_test_session")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run the flat manual transcript and all service scenarios.",
    )
    parser.add_argument(
        "--service-scenarios",
        action="store_true",
        help="Run deterministic service purchase scenarios.",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", *sorted(SERVICE_SCENARIOS.keys())],
        help="Run one named service scenario.",
    )
    parser.add_argument(
        "--turn",
        action="append",
        default=[],
        help="Override scripted turns. Can be passed multiple times.",
    )

    args = parser.parse_args()

    turns = args.turn or MANUAL_TEST_TURNS

    if args.all:
        run_manual_transcript(turns, session_id=args.session_id)
        run_service_scenarios("all")
        return

    if args.service_scenarios:
        run_service_scenarios(args.scenario)
        return

    run_manual_transcript(turns, session_id=args.session_id)
    return


if __name__ == "__main__":
    main()
