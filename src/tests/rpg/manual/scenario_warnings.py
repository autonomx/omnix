from __future__ import annotations

import json
from typing import Any, Dict, List

from tests.rpg.manual.output_state import (
    _REGRESSION_WARNING_LOCK,
    _REGRESSION_WARNING_ROWS,
    _REGRESSION_WARNINGS,
)
from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str
from tests.rpg.manual.scenario_summary import (
    _extract_service_memories,
    _extract_simulation_state,
    _pre_turn_contamination_snapshot,
)


def _reset_regression_warnings() -> None:
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNING_ROWS.clear()
        _REGRESSION_WARNINGS.clear()


def _record_regression_warnings(row: Dict[str, Any]) -> None:
    warnings = _safe_list(row.get("regression_warnings")) + _safe_list(row.get("scenario_warnings"))
    if warnings:
        with _REGRESSION_WARNING_LOCK:
            _REGRESSION_WARNING_ROWS.append(row)


def _record_scenario_error(
    *,
    scenario_name: str,
    session_id: str = "",
    error: str,
) -> None:
    row = {
        "scenario": scenario_name,
        "session_id": session_id,
        "turn": 0,
        "player_input": "",
        "scenario_warnings": [f"scenario_runtime_error:{scenario_name}:{error}"],
        "regression_warnings": [f"scenario_runtime_error:{scenario_name}:{error}"],
    }
    with _REGRESSION_WARNING_LOCK:
        _REGRESSION_WARNING_ROWS.append(row)


def _add_regression_warning(
    *,
    regression_warnings: List[str] | None = None,
    warning: str,
    scenario: str | None = None,
    turn: int | None = None,
) -> None:
    if regression_warnings is not None:
        regression_warnings.append(warning)
    elif scenario is not None and turn is not None:
        warning_entry = f"{scenario}:turn_{turn}:{warning}"
        with _REGRESSION_WARNING_LOCK:
            _REGRESSION_WARNINGS.append(warning_entry)
    else:
        raise ValueError("Either regression_warnings or (scenario and turn) must be provided")


def _extract_turn_grounding_validation(turn_record: Dict[str, Any]) -> Dict[str, Any]:
    turn_record = _safe_dict(turn_record)

    for candidate in (
        turn_record.get("grounding_validation"),
        _safe_dict(turn_record.get("narration_debug")).get("grounding_validation"),
        _safe_dict(turn_record.get("extracted")).get("grounding_validation"),
        _safe_dict(turn_record.get("result")).get("grounding_validation"),
        _safe_dict(_safe_dict(turn_record.get("result")).get("result")).get("grounding_validation"),
    ):
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate

    return {}


def _n101_grounding_warnings(
    *,
    scenario_name: str,
    turn_index: int,
    turn_record: Dict[str, Any],
) -> List[str]:
    warnings: List[str] = []
    grounding = _extract_turn_grounding_validation(turn_record)
    has_narration = bool(
        _safe_str(turn_record.get("narration_preview"))
        or _safe_dict(turn_record.get("narration_debug"))
        or _safe_dict(turn_record.get("extracted"))
    )

    if has_narration and not grounding:
        warnings.append(f"{scenario_name}:turn_{turn_index}:missing_grounding_validation")
        return warnings

    if bool(grounding.get("fallback_used")):
        source = _safe_str(grounding.get("fallback_source") or "unknown")
        selected = _safe_str(grounding.get("selected_candidate") or "unknown")
        warnings.append(f"{scenario_name}:turn_{turn_index}:grounding_fallback_used:{source}:{selected}")

    for violation in _safe_list(grounding.get("violations")):
        code = _safe_str(_safe_dict(violation).get("code")).strip()
        if code:
            warnings.append(f"{scenario_name}:turn_{turn_index}:grounding_violation:{code}")

    for violation in _safe_list(grounding.get("primary_violations")):
        code = _safe_str(_safe_dict(violation).get("code")).strip()
        if code:
            warnings.append(f"{scenario_name}:turn_{turn_index}:grounding_primary_violation:{code}")

    return warnings


def _turn_text_blob(turn_record: Dict[str, Any]) -> str:
    pieces: List[str] = []
    for key in ("narration_preview",):
        value = _safe_str(_safe_dict(turn_record).get(key))
        if value:
            pieces.append(value)

    narration_debug = _safe_dict(_safe_dict(turn_record).get("narration_debug"))
    for key in ("final_narration", "json_narration", "json_action", "npc_line"):
        value = _safe_str(narration_debug.get(key))
        if value:
            pieces.append(value)

    extracted = _safe_dict(_safe_dict(turn_record).get("extracted"))
    for key in ("narration", "action", "npc_line"):
        value = _safe_str(extracted.get(key))
        if value:
            pieces.append(value)

    return "\n".join(pieces).lower()


def _text_blob_from_turn(turn_record: Dict[str, Any]) -> str:
    pieces: List[str] = []

    for key in ("narration_preview",):
        value = _safe_str(_safe_dict(turn_record).get(key))
        if value:
            pieces.append(value)

    narration_debug = _safe_dict(_safe_dict(turn_record).get("narration_debug"))
    for key in ("final_narration", "json_narration", "json_action", "npc_line"):
        value = _safe_str(narration_debug.get(key))
        if value:
            pieces.append(value)

    extracted = _safe_dict(_safe_dict(turn_record).get("extracted"))
    for key in ("narration", "action", "npc_line"):
        value = _safe_str(extracted.get(key))
        if value:
            pieces.append(value)

    return "\n".join(pieces).lower()


def _is_n101_gate_warning(value: Any) -> bool:
    text = _safe_str(value).lower()
    if not text:
        return False

    # This scenario intentionally proves the validator catches bad combat narration.
    # Deterministic fallback is expected here and should not fail the N101 gate.
    if "narration_validator_catches_hit_miss_contradiction" in text:
        if (
            "unsupported_combat_claim" in text
            or "grounding_fallback_used:deterministic_fallback" in text
        ):
            return False

    hard_markers = (
        ":n101_",
        "n101_",
        "fake_debt_",
        "provider_json_parse_failed",
        "provider_context_exceeded",
        "provider_call_failed",
    )
    if any(marker in text for marker in hard_markers):
        return True

    # Grounding fallback is a gate failure for fake-debt, not for the combat contradiction test.
    if "npc_bran_refuses_fake_debt" in text:
        markers = (
            "grounding_violation:",
            "grounding_primary_violation:",
            "grounding_fallback_used:",
            "unsupported_reward_claim",
            "unsupported_debt",
            "deterministic_fallback",
        )
        return any(marker in text for marker in markers)

    return False


def _promote_turn_scenario_warnings(
    *,
    turn_summaries: List[Dict[str, Any]],
    scenario_warnings: List[str],
    regression_warnings: List[str],
) -> None:
    for turn_record in turn_summaries:
        for warning in _safe_list(_safe_dict(turn_record).get("scenario_warnings")):
            warning_text = _safe_str(warning)
            if not warning_text:
                continue

            if warning_text not in scenario_warnings:
                scenario_warnings.append(warning_text)

            if _is_n101_gate_warning(warning_text):
                _add_regression_warning(
                    regression_warnings=regression_warnings,
                    warning=warning_text,
                )


def _n101_stabilization_gate_warnings(
    *,
    scenario_name: str,
    turn_index: int,
    turn_record: Dict[str, Any],
) -> List[str]:
    warnings: List[str] = []
    grounding = _extract_turn_grounding_validation(turn_record)
    text = _text_blob_from_turn(turn_record)

    if not grounding:
        warnings.append("n101_missing_grounding_validation")
        return warnings

    selected = _safe_str(grounding.get("selected_candidate"))
    fallback_source = _safe_str(grounding.get("fallback_source"))

    if selected not in {"primary", "safe_fallback", "deterministic_fallback", "first_call_visible_response"}:
        warnings.append(f"n101_invalid_selected_candidate:{selected or 'missing'}")

    # Candidate JSON/provider health.
    narration_debug = _safe_dict(turn_record.get("narration_debug"))
    provider_diagnostics = _safe_dict(narration_debug.get("provider_call_diagnostics"))
    if provider_diagnostics:
        if provider_diagnostics.get("parsed_json_ok") is False:
            warnings.append("n101_provider_json_parse_failed")
        if provider_diagnostics.get("provider_valid") is False:
            warnings.append("n101_provider_invalid")

        provider_error_blob = json.dumps(provider_diagnostics, ensure_ascii=False).lower()
        if "context size has been exceeded" in provider_error_blob or "context" in provider_error_blob and "exceeded" in provider_error_blob:
            warnings.append("n101_provider_context_exceeded")

        if "provider_call_failed" in provider_error_blob:
            warnings.append("n101_provider_call_failed")

    narration_debug_blob = json.dumps(narration_debug, ensure_ascii=False).lower()
    if "context size has been exceeded" in narration_debug_blob:
        warnings.append("n101_provider_context_exceeded")

    # Fake debt must never grant or imply payment.
    if scenario_name == "npc_bran_refuses_fake_debt":
        grant_phrases = (
            "here is 50 gold",
            "here's 50 gold",
            "hands you 50 gold",
            "gives you 50 gold",
            "you receive 50 gold",
            "you gain 50 gold",
            "paid you 50 gold",
        )
        if any(phrase in text for phrase in grant_phrases):
            warnings.append("n101_fake_debt_printed_grant_language")

        refusal_terms = (
            "do not owe",
            "don't owe",
            "does not owe",
            "not owe",
            "no coin",
            "no gold",
            "no payment",
            "cannot agree",
            "won't pay",
            "will not pay",
            "refuse",
        )
        if "50 gold" in text and not any(term in text for term in refusal_terms):
            warnings.append("n101_fake_debt_mentions_50_gold_without_refusal")

        if fallback_source == "deterministic_fallback":
            warnings.append("n101_fake_debt_used_deterministic_fallback")

    # Unpaid room should allow price quotes, but must clearly refuse free service.
    if scenario_name == "npc_bran_refuses_unpaid_room":
        price_quote_terms = ("silver", "gold", "coin", "coins", "gp", "sp", "cp")
        has_price_quote = any(term in text for term in price_quote_terms)
        price_false_positive = any(
            _safe_str(_safe_dict(v).get("code")) == "unsupported_reward_claim"
            for v in _safe_list(grounding.get("primary_violations"))
        )
        if has_price_quote and price_false_positive:
            warnings.append("n101_price_quote_false_positive")

        soft_accept_terms = (
            "let me check",
            "maybe",
            "perhaps",
            "we'll see",
            "we will see",
            "i can arrange",
            "available for you",
        )
        clear_refusal_terms = (
            "no free",
            "not free",
            "pay",
            "cost",
            "price",
            "rate",
            "refuse",
            "won't",
            "cannot",
            "can't",
        )
        if any(term in text for term in soft_accept_terms) and not any(term in text for term in clear_refusal_terms):
            warnings.append("n101_unpaid_room_soft_acceptance")

    # Hit/miss contradiction should trigger fallback or explicit rejection if bad combat text appears.
    if scenario_name == "narration_validator_catches_hit_miss_contradiction":
        combat_bad_terms = ("kills", "dead", "blood", "wound", "damage")
        if any(term in text for term in combat_bad_terms):
            # If it appears, it must have been authorized by combat delta or selected fallback metadata.
            if not grounding.get("fallback_used"):
                warnings.append("n101_possible_unsupported_combat_text")

    return warnings


def _build_n101_grounding_summary(turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "turns_checked": 0,
        "missing_grounding_validation": 0,
        "selected_candidate_counts": {},
        "fallback_source_counts": {},
        "fallback_used_count": 0,
        "violation_counts": {},
        "primary_violation_counts": {},
        "provider_json_parse_failed_count": 0,
        "provider_invalid_count": 0,
        "background_soft_correction_count": 0,
    }

    for turn in turns:
        grounding = _extract_turn_grounding_validation(turn)
        if not grounding:
            summary["missing_grounding_validation"] += 1
            continue

        summary["turns_checked"] += 1

        selected = _safe_str(grounding.get("selected_candidate") or "unknown")
        summary["selected_candidate_counts"][selected] = (
            int(summary["selected_candidate_counts"].get(selected, 0)) + 1
        )

        source = _safe_str(grounding.get("fallback_source") or "none")
        summary["fallback_source_counts"][source] = (
            int(summary["fallback_source_counts"].get(source, 0)) + 1
        )

        if bool(grounding.get("fallback_used")):
            summary["fallback_used_count"] += 1

        for violation in _safe_list(grounding.get("violations")):
            code = _safe_str(_safe_dict(violation).get("code") or "unknown")
            summary["violation_counts"][code] = int(summary["violation_counts"].get(code, 0)) + 1

        for violation in _safe_list(grounding.get("primary_violations")):
            code = _safe_str(_safe_dict(violation).get("code") or "unknown")
            summary["primary_violation_counts"][code] = int(summary["primary_violation_counts"].get(code, 0)) + 1

        narration_debug = _safe_dict(turn.get("narration_debug"))
        provider_diagnostics = _safe_dict(narration_debug.get("provider_call_diagnostics"))
        if provider_diagnostics.get("parsed_json_ok") is False:
            summary["provider_json_parse_failed_count"] += 1
        if provider_diagnostics.get("provider_valid") is False:
            summary["provider_invalid_count"] += 1

        if turn.get("role") == "grounding_soft_correction":
            summary["background_soft_correction_count"] += 1

    return summary


def _currency_delta_found(turn_record: Dict[str, Any]) -> bool:
    """Detect actual authoritative/final currency or reward grants.

    Do not scan raw provider response, rejected primary candidates, primary_violations,
    raw_narration_candidates, or diagnostic blobs. Fake-debt tests intentionally include
    rejected text like "Here is 50 gold" in diagnostics.
    """
    turn_record = _safe_dict(turn_record)

    # 1. Final selected structured payload only.
    extracted = _safe_dict(turn_record.get("extracted"))
    reward = extracted.get("reward")
    if reward not in (None, "", {}, []):
        return True

    final_text = _turn_text_blob(turn_record)
    grant_terms = (
        "here is 50 gold",
        "here's 50 gold",
        "hands you 50 gold",
        "gives you 50 gold",
        "you receive 50 gold",
        "you gain 50 gold",
        "paid you 50 gold",
    )
    if any(term in final_text for term in grant_terms):
        return True

    # 2. Final selected narration JSON only. Explicitly ignore raw_narration_candidates.
    structured = _safe_dict(turn_record.get("structured_narration_compact"))
    for key in ("reward", "currency_delta", "money_delta", "inventory_delta", "items_added"):
        value = structured.get(key)
        if value not in (None, "", {}, []):
            return True

    narration_payload = _safe_dict(turn_record.get("narration_payload_compact"))
    selected_only = {
        key: value
        for key, value in narration_payload.items()
        if key
        not in {
            "raw_narration_candidates",
            "raw_provider_response",
            "provider_call_diagnostics",
            "grounding_validation",
            "primary_violations",
        }
    }
    for key in ("reward", "currency_delta", "money_delta", "inventory_delta", "items_added"):
        value = selected_only.get(key)
        if value not in (None, "", {}, []):
            return True

    # 3. Authoritative compact deltas only.
    for source_key in ("compact_state_deltas",):
        source = _safe_dict(turn_record.get(source_key))
        for key in ("currency_delta", "money_delta", "inventory_delta", "items_added", "reward"):
            value = source.get(key)
            if value not in (None, "", {}, []):
                return True

    # 4. Resolved result/contract deltas only, not raw candidate text.
    for source_key in ("resolved_result_compact", "turn_contract_compact"):
        source = _safe_dict(turn_record.get(source_key))
        for key in ("currency_delta", "money_delta", "inventory_delta", "items_added", "reward"):
            value = source.get(key)
            if value not in (None, "", {}, []):
                return True

    return False


def _fake_debt_expectation_warnings(
    *,
    scenario_name: str,
    turn_index: int,
    turn_record: Dict[str, Any],
) -> List[str]:
    if scenario_name != "npc_bran_refuses_fake_debt":
        return []

    warnings: List[str] = []
    text = _turn_text_blob(turn_record)
    grounding = _extract_turn_grounding_validation(turn_record)
    selected = _safe_str(grounding.get("selected_candidate"))
    fallback_source = _safe_str(grounding.get("fallback_source"))

    if not grounding:
        warnings.append("fake_debt_missing_grounding_validation")
    elif selected not in {"primary", "safe_fallback"}:
        warnings.append(f"fake_debt_unexpected_selected_candidate:{selected or 'missing'}")

    provider_failed = False
    narration_debug = _safe_dict(turn_record.get("narration_debug"))
    provider_diagnostics = _safe_dict(narration_debug.get("provider_call_diagnostics"))
    provider_blob = json.dumps(provider_diagnostics, ensure_ascii=False).lower()
    if (
        provider_diagnostics.get("provider_valid") is False
        or "provider_call_failed" in provider_blob
        or "context size has been exceeded" in provider_blob
        or "provider_json_parse_failed" in provider_blob
    ):
        provider_failed = True

    if fallback_source == "deterministic_fallback" and not provider_failed:
        warnings.append("fake_debt_used_deterministic_fallback")

    if _currency_delta_found(turn_record):
        warnings.append("fake_debt_currency_or_reward_delta_detected")

    # Mentioning debt/gold terms is okay only if it is clearly refused/deferred.
    mentions_debt_or_gold = (
        "50 gold" in text
        or "fifty gold" in text
        or "owe" in text
        or "debt" in text
        or "coin" in text
        or "payment" in text
    )
    refusal_terms = (
        "do not owe",
        "don't owe",
        "does not owe",
        "no coin",
        "no gold",
        "no payment",
        "not owe",
        "cannot agree",
        "won't pay",
        "will not pay",
        "unsupported",
        "claim",
        "refused",
        "refuses",
    )
    if mentions_debt_or_gold and not any(term in text for term in refusal_terms):
        warnings.append("fake_debt_mentions_debt_without_refusal")

    grant_terms = (
        "here is 50 gold",
        "here's 50 gold",
        "hands you 50 gold",
        "gives you 50 gold",
        "you receive 50 gold",
        "you gain 50 gold",
    )
    if any(term in text for term in grant_terms):
        warnings.append("fake_debt_printed_grant_language")

    bad_debt_confirmation_terms = (
        "acknowledges the debt",
        "acknowledge the debt",
        "confirms the debt",
        "admits the debt",
        "outstanding amount",
        "outstanding debt",
        "payment is due",
        "valid debt",
        "real debt",
    )
    if any(term in text for term in bad_debt_confirmation_terms):
        warnings.append("fake_debt_confirmed_or_acknowledged_unsupported_debt")

    return warnings


def _scenario_contamination_warnings(
    *,
    scenario_name: str,
    turn_index: int,
    before_currency: Dict[str, Any],
    before_items: List[Dict[str, Any]],
    result: Dict[str, Any],
    pre_turn_snapshot: Dict[str, int],
    allows_seeded_world_events: bool,
    allows_seeded_journal_entries: bool,
    allows_seeded_quest_state: bool,
) -> List[str]:
    """Check for scenario contamination warnings."""
    warnings: List[str] = []

    after_snapshot = _pre_turn_contamination_snapshot(_extract_simulation_state(result))

    if not allows_seeded_world_events:
        if after_snapshot["world_event_count"] > pre_turn_snapshot["world_event_count"]:
            warnings.append("unexpected_world_event_creation")

    if not allows_seeded_journal_entries:
        if after_snapshot["journal_entry_count"] > pre_turn_snapshot["journal_entry_count"]:
            warnings.append("unexpected_journal_entry_creation")

    if not allows_seeded_quest_state:
        if after_snapshot["quest_count"] > pre_turn_snapshot["quest_count"]:
            warnings.append("unexpected_quest_creation")

    allows_service_memories = scenario_name in {
        "npc_bran_refuses_unpaid_room",
        "npc_bran_negotiates_high_trust_room",
        "npc_bran_escalates_when_threatened",
    }

    service_memories = _extract_service_memories(result)
    if service_memories and not allows_service_memories:
        warnings.append("unexpected_service_memory_creation")

    return warnings
