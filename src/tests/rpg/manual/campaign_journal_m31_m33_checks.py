from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_journal.journal import (
    build_campaign_journal,
    build_player_story_recap,
    record_campaign_journal_entry,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_simulation_state(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    session_dict = _safe_dict(session)
    session_setup_payload = _safe_dict(session_dict.get("setup_payload"))
    session_metadata = _safe_dict(session_setup_payload.get("metadata"))

    candidates = [
        session_dict.get("simulation_state"),
        session_metadata.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        _safe_dict(nested.get("session")).get("simulation_state"),
        result.get("simulation_state"),
        nested.get("simulation_state"),
    ]

    first_non_empty: Dict[str, Any] = {}
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate and not first_non_empty:
            first_non_empty = candidate
        if (
            isinstance(candidate.get("campaign_journal_state"), dict)
            or isinstance(candidate.get("story_arc_state"), dict)
            or isinstance(candidate.get("lore_state"), dict)
            or isinstance(candidate.get("story_event_state"), dict)
            or isinstance(candidate.get("npc_evolution_state"), dict)
            or isinstance(candidate.get("party_state"), dict)
        ):
            return candidate
    return first_non_empty


def run_campaign_journal_m31_m33_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "campaign_journal_record":
        record_result = record_campaign_journal_entry(
            simulation_state,
            kind=str(check.get("kind") or "story"),
            title=str(check.get("title") or ""),
            summary=str(check.get("summary") or ""),
            turn_index=int(check.get("turn_index") or 1),
            visibility=str(check.get("visibility") or "player"),
            fact_status=str(check.get("fact_status") or ""),
            arc_ids=check.get("arc_ids") or [],
            lore_ids=check.get("lore_ids") or [],
            event_ids=check.get("event_ids") or [],
            npc_ids=check.get("npc_ids") or [],
            quest_ids=check.get("quest_ids") or [],
            tags=check.get("tags") or [],
            source_id=str(check.get("source_id") or ""),
        )
        expected_ok = check.get("expected_ok")
        ok = True
        if expected_ok is not None:
            ok = ok and record_result.get("ok") is bool(expected_ok)
        return {
            "check_type": check_type,
            "ok": ok,
            "record_result": record_result,
        }

    if check_type == "campaign_journal_contains":
        journal = build_campaign_journal(
            simulation_state,
            include_hidden=bool(check.get("include_hidden", False)),
            max_entries=int(check.get("max_entries") or 25),
        )
        expected_summary_contains = str(check.get("expected_summary_contains") or "")
        expected_kind = check.get("expected_kind")
        rows = list(journal.get("entries") or [])
        if expected_kind:
            rows = [row for row in rows if row.get("kind") == expected_kind]
        if expected_summary_contains:
            rows = [row for row in rows if expected_summary_contains in str(row.get("summary") or "")]
        return {
            "check_type": check_type,
            "ok": bool(rows),
            "journal": journal,
            "matched": rows,
            "expected_summary_contains": expected_summary_contains,
            "expected_kind": expected_kind,
        }

    if check_type == "campaign_journal_lore":
        journal = build_campaign_journal(simulation_state)
        lore_id = str(check.get("lore_id") or "")
        expected_present = bool(check.get("expected_present", True))
        expected_truth_status = check.get("expected_truth_status")
        rows = [row for row in journal.get("known_lore") or [] if row.get("lore_id") == lore_id]
        ok = bool(rows) is expected_present
        if rows and expected_truth_status:
            ok = ok and rows[0].get("truth_status") == expected_truth_status
        return {
            "check_type": check_type,
            "ok": ok,
            "lore_id": lore_id,
            "expected_present": expected_present,
            "expected_truth_status": expected_truth_status,
            "matched": rows,
            "known_lore": journal.get("known_lore"),
        }

    if check_type == "campaign_story_recap":
        recap = build_player_story_recap(
            simulation_state,
            turn_index=int(check.get("turn_index") or 1),
            max_items=int(check.get("max_items") or 25),
        )
        expected_arc_id = check.get("expected_arc_id")
        expected_pending_event_id = check.get("expected_pending_event_id")
        expected_npc_id = check.get("expected_npc_id")
        expected_party_npc_id = check.get("expected_party_npc_id")
        ok = True
        if expected_arc_id:
            ok = ok and expected_arc_id in [row.get("arc_id") for row in recap.get("active_arcs") or []]
        if expected_pending_event_id:
            ok = ok and expected_pending_event_id in [row.get("event_id") for row in recap.get("pending_consequences") or []]
        if expected_npc_id:
            ok = ok and expected_npc_id in [row.get("npc_id") for row in recap.get("npc_evolution") or []]
        if expected_party_npc_id:
            ok = ok and expected_party_npc_id in [row.get("npc_id") for row in recap.get("party") or []]
        return {
            "check_type": check_type,
            "ok": ok,
            "recap": recap,
            "expected_arc_id": expected_arc_id,
            "expected_pending_event_id": expected_pending_event_id,
            "expected_npc_id": expected_npc_id,
            "expected_party_npc_id": expected_party_npc_id,
        }

    if check_type == "campaign_story_recap_bounded":
        max_items = int(check.get("max_items") or 10)
        recap = build_player_story_recap(simulation_state, turn_index=int(check.get("turn_index") or 1), max_items=max_items)
        ok = (
            len(recap.get("latest_journal_entries") or []) <= max_items
            and len(recap.get("active_arcs") or []) <= max_items
            and len(recap.get("known_lore") or []) <= max_items
            and len(recap.get("pending_consequences") or []) <= max_items
            and len(recap.get("npc_evolution") or []) <= max_items
            and len(recap.get("party") or []) <= max_items
        )
        return {
            "check_type": check_type,
            "ok": ok,
            "max_items": max_items,
            "recap": recap,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_campaign_journal_m31_m33_check_type:{check_type}",
    }


def run_campaign_journal_m31_m33_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_campaign_journal_m31_m33_check(check=check, result=result, session=session)
        for check in checks
    ]