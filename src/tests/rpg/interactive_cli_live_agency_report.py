"""Phase 14.23 — deterministic live next-action agency report.

This report inspects interactive transcript/result payloads for the Phase 14.19–14.21
player-agency contract without calling an LLM. It is intentionally independent of
runtime execution: it validates that successful live turns expose useful
presentation-only next actions and button payloads while preserving runtime
validation boundaries.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

LIVE_AGENCY_REPORT_VERSION = "rpg_live_agency_report_v1"
LIVE_AGENCY_AGGREGATE_VERSION = "rpg_live_agency_report_aggregate_v1"
LIVE_AGENCY_STATUS_MARKER = "RPG_LIVE_AGENCY_REPORT"
MIN_NEXT_ACTION_COVERAGE_RATIO = 0.95
MIN_BUTTON_COVERAGE_RATIO = 0.95


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _extract_turns(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    turns = payload.get("turns")
    if isinstance(turns, list):
        return [_safe_dict(turn) for turn in turns]
    transcript = _safe_dict(payload.get("transcript"))
    turns = transcript.get("turns")
    if isinstance(turns, list):
        return [_safe_dict(turn) for turn in turns]
    result = _safe_dict(payload.get("result"))
    turns = result.get("turns")
    if isinstance(turns, list):
        return [_safe_dict(turn) for turn in turns]
    return []


def _raw_sources(turn: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    nested = _safe_dict(raw.get("result"))
    return [_safe_dict(turn), raw, nested]


def _first_contract(turn: Mapping[str, Any]) -> dict[str, Any]:
    for source in _raw_sources(turn):
        contract = _safe_dict(source.get("next_actions") or source.get("player_agency_contract"))
        if contract:
            return contract
    return {}


def _first_buttons(turn: Mapping[str, Any]) -> dict[str, Any]:
    for source in _raw_sources(turn):
        buttons = _safe_dict(source.get("next_action_buttons"))
        if buttons:
            return buttons
    return {}


def _option_items(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_safe_dict(item) for item in _safe_list(_safe_dict(contract).get("options")) if _safe_dict(item)]


def _button_items(buttons: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_safe_dict(item) for item in _safe_list(_safe_dict(buttons).get("buttons")) if _safe_dict(item)]


def _duplicate_ids(items: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for item in items:
        item_id = _safe_str(item.get("id")).strip()
        if not item_id:
            continue
        if item_id in seen:
            dupes.add(item_id)
        seen.add(item_id)
    return sorted(dupes)


def evaluate_turn_agency_payload(turn: Mapping[str, Any], *, turn_index: int = 0) -> dict[str, Any]:
    contract = _first_contract(turn)
    buttons = _first_buttons(turn)
    options = _option_items(contract)
    button_items = _button_items(buttons)
    option_ids = [_safe_str(option.get("id")).strip() for option in options if _safe_str(option.get("id")).strip()]
    button_ids = [_safe_str(button.get("id")).strip() for button in button_items if _safe_str(button.get("id")).strip()]
    empty_option_commands = [_safe_str(option.get("id") or f"option_{index}") for index, option in enumerate(options, start=1) if not _safe_str(option.get("command")).strip()]
    empty_button_commands = [_safe_str(button.get("id") or f"button_{index}") for index, button in enumerate(button_items, start=1) if not _safe_str(button.get("submit_command") or button.get("command")).strip()]
    mutated_button_commands = []
    options_by_id = {option_id: option for option_id, option in zip(option_ids, options) if option_id}
    for button in button_items:
        button_id = _safe_str(button.get("id")).strip()
        if not button_id or button_id not in options_by_id:
            continue
        option_command = _safe_str(options_by_id[button_id].get("command")).strip()
        submit_command = _safe_str(button.get("submit_command") or button.get("command")).strip()
        if option_command and submit_command and option_command != submit_command:
            mutated_button_commands.append(button_id)
    button_without_option = sorted(set(button_ids) - set(option_ids))
    option_without_button = sorted(set(option_ids) - set(button_ids))
    invalid_options = [
        _safe_str(option.get("id") or f"option_{index}")
        for index, option in enumerate(options, start=1)
        if option.get("validation_required") is not True or option.get("presentation_only") is not True
    ]
    invalid_buttons = [
        _safe_str(button.get("id") or f"button_{index}")
        for index, button in enumerate(button_items, start=1)
        if button.get("validation_required") is not True or button.get("presentation_only") is not True
    ]
    failures: list[str] = []
    warnings: list[str] = []
    if not options:
        failures.append("next_actions_missing_or_empty")
    if not button_items:
        failures.append("next_action_buttons_missing_or_empty")
    if empty_option_commands:
        failures.append("next_action_option_empty_command")
    if empty_button_commands:
        failures.append("next_action_button_empty_submit_command")
    if invalid_options:
        failures.append("next_action_option_validation_or_presentation_flag_invalid")
    if invalid_buttons:
        failures.append("next_action_button_validation_or_presentation_flag_invalid")
    if _duplicate_ids(options):
        failures.append("next_action_duplicate_option_ids")
    if _duplicate_ids(button_items):
        failures.append("next_action_duplicate_button_ids")
    if mutated_button_commands:
        failures.append("next_action_button_submit_command_mismatch")
    if button_without_option:
        failures.append("next_action_button_without_option")
    if option_without_button:
        warnings.append("next_action_option_without_button")
    tone_tags = sorted({tag for button in button_items for tag in [_safe_str(item).strip() for item in _safe_list(button.get("tone_tags"))] if tag})
    return {
        "turn_index": int(turn.get("turn_index") or turn_index or 0),
        "player_input": _safe_str(turn.get("player_input"))[:500],
        "ok": not failures,
        "option_count": len(options),
        "button_count": len(button_items),
        "option_ids": option_ids,
        "button_ids": button_ids,
        "tone_tags": tone_tags[:12],
        "failures": sorted(set(failures)),
        "warnings": sorted(set(warnings)),
        "details": {
            "empty_option_commands": empty_option_commands,
            "empty_button_commands": empty_button_commands,
            "invalid_options": invalid_options,
            "invalid_buttons": invalid_buttons,
            "duplicate_option_ids": _duplicate_ids(options),
            "duplicate_button_ids": _duplicate_ids(button_items),
            "mutated_button_commands": mutated_button_commands,
            "button_without_option": button_without_option,
            "option_without_button": option_without_button,
        },
    }


def evaluate_live_agency_payload(transcript_or_result: Mapping[str, Any]) -> dict[str, Any]:
    turns = _extract_turns(transcript_or_result)
    per_turn = [evaluate_turn_agency_payload(turn, turn_index=index) for index, turn in enumerate(turns, start=1)]
    turn_count = len(per_turn)
    covered_turns = sum(1 for item in per_turn if int(item.get("option_count") or 0) > 0)
    button_turns = sum(1 for item in per_turn if int(item.get("button_count") or 0) > 0)
    passed_turns = sum(1 for item in per_turn if bool(item.get("ok")))
    failures: list[str] = []
    warnings: list[str] = []
    for item in per_turn:
        for failure in _safe_list(item.get("failures")):
            failures.append(f"turn_{int(item.get('turn_index') or 0)}_{_safe_str(failure)}")
        for warning in _safe_list(item.get("warnings")):
            warnings.append(f"turn_{int(item.get('turn_index') or 0)}_{_safe_str(warning)}")
    if turn_count == 0:
        failures.append("agency_report_has_no_turns")
    next_action_coverage_ratio = round(covered_turns / turn_count, 4) if turn_count else 0.0
    button_coverage_ratio = round(button_turns / turn_count, 4) if turn_count else 0.0
    if turn_count and next_action_coverage_ratio < MIN_NEXT_ACTION_COVERAGE_RATIO:
        failures.append("next_action_coverage_ratio_below_threshold")
    if turn_count and button_coverage_ratio < MIN_BUTTON_COVERAGE_RATIO:
        failures.append("next_action_button_coverage_ratio_below_threshold")
    return {
        "format_version": LIVE_AGENCY_REPORT_VERSION,
        "ok": not failures,
        "turn_count": turn_count,
        "passed_turn_count": passed_turns,
        "failed_turn_count": turn_count - passed_turns,
        "thresholds": {
            "min_next_action_coverage_ratio": MIN_NEXT_ACTION_COVERAGE_RATIO,
            "min_button_coverage_ratio": MIN_BUTTON_COVERAGE_RATIO,
        },
        "signals": {
            "next_action_turn_count": covered_turns,
            "next_action_coverage_ratio": next_action_coverage_ratio,
            "next_action_button_turn_count": button_turns,
            "next_action_button_coverage_ratio": button_coverage_ratio,
            "total_option_count": sum(int(item.get("option_count") or 0) for item in per_turn),
            "total_button_count": sum(int(item.get("button_count") or 0) for item in per_turn),
        },
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "failures": sorted(set(failures))[:200],
        "warnings": sorted(set(warnings))[:200],
        "turns": per_turn,
    }


def read_live_agency_payload(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.exists():
        return {"format_version": LIVE_AGENCY_REPORT_VERSION, "ok": False, "error": "transcript_missing", "source_path": str(candidate)}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"format_version": LIVE_AGENCY_REPORT_VERSION, "ok": False, "error": "transcript_json_invalid", "source_path": str(candidate)}
    if not isinstance(payload, Mapping):
        return {"format_version": LIVE_AGENCY_REPORT_VERSION, "ok": False, "error": "transcript_payload_not_object", "source_path": str(candidate)}
    result = evaluate_live_agency_payload(payload)
    result["source_path"] = str(candidate)
    return result


def write_live_agency_report(*, result: Mapping[str, Any], report_path: str | Path) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return path


def aggregate_live_agency_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    total_turn_count = 0
    passed = 0
    failed = 0
    all_failures: list[str] = []
    all_warnings: list[str] = []
    total_next_action_turns = 0
    total_button_turns = 0
    total_options = 0
    total_buttons = 0
    for index, report in enumerate(reports):
        payload = dict(report)
        ok = payload.get("format_version") == LIVE_AGENCY_REPORT_VERSION and bool(payload.get("ok"))
        turn_count = int(payload.get("turn_count") or 0)
        signals = _safe_dict(payload.get("signals"))
        total_turn_count += turn_count
        total_next_action_turns += int(signals.get("next_action_turn_count") or 0)
        total_button_turns += int(signals.get("next_action_button_turn_count") or 0)
        total_options += int(signals.get("total_option_count") or 0)
        total_buttons += int(signals.get("total_button_count") or 0)
        failures = [_safe_str(item) for item in _safe_list(payload.get("failures")) if _safe_str(item)]
        warnings = [_safe_str(item) for item in _safe_list(payload.get("warnings")) if _safe_str(item)]
        all_failures.extend(failures)
        all_warnings.extend(warnings)
        passed += 1 if ok else 0
        failed += 0 if ok else 1
        entries.append(
            {
                "index": index,
                "ok": ok,
                "turn_count": turn_count,
                "failure_count": len(failures),
                "warning_count": len(warnings),
                "next_action_coverage_ratio": float(signals.get("next_action_coverage_ratio") or 0.0),
                "button_coverage_ratio": float(signals.get("next_action_button_coverage_ratio") or 0.0),
                "source_path": _safe_str(payload.get("source_path")),
            }
        )
    return {
        "aggregate_format_version": LIVE_AGENCY_AGGREGATE_VERSION,
        "ok": failed == 0,
        "summary_count": len(reports),
        "passed": passed,
        "failed": failed,
        "total_turn_count": total_turn_count,
        "signals": {
            "next_action_turn_count": total_next_action_turns,
            "next_action_coverage_ratio": round(total_next_action_turns / total_turn_count, 4) if total_turn_count else 0.0,
            "next_action_button_turn_count": total_button_turns,
            "next_action_button_coverage_ratio": round(total_button_turns / total_turn_count, 4) if total_turn_count else 0.0,
            "total_option_count": total_options,
            "total_button_count": total_buttons,
        },
        "failure_count": len(all_failures),
        "warning_count": len(all_warnings),
        "failure_types": sorted(set(all_failures))[:200],
        "warning_types": sorted(set(all_warnings))[:200],
        "entries": entries,
    }


def render_live_agency_status_marker(result: Mapping[str, Any]) -> str:
    ok = "true" if bool(result.get("ok")) else "false"
    turn_count = int(result.get("turn_count") or result.get("total_turn_count") or 0)
    signals = _safe_dict(result.get("signals"))
    coverage = float(signals.get("next_action_coverage_ratio") or 0.0)
    button_coverage = float(signals.get("next_action_button_coverage_ratio") or 0.0)
    error = _safe_str(result.get("error") or (_safe_list(result.get("failures")) or _safe_list(result.get("failure_types")) or ["none"])[0])
    return f"[{LIVE_AGENCY_STATUS_MARKER}] ok={ok} turn_count={turn_count} next_actions={coverage:.3f} buttons={button_coverage:.3f} error={error}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate live RPG next-action agency payloads without calling an LLM.")
    parser.add_argument("transcript_path", nargs="?", help="Path to interactive-transcript.json or compatible JSON payload.")
    parser.add_argument("--summary-path", default="", help="Optional path to persist the agency report JSON.")
    parser.add_argument("--aggregate-summary", action="append", default=[], help="Persisted agency report JSON to include in aggregate mode; may be repeated.")
    parser.add_argument("--aggregate-path", default="", help="Optional path to persist aggregate mode JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.aggregate_summary:
        reports = [read_live_agency_payload(path) for path in args.aggregate_summary]
        result = aggregate_live_agency_reports(reports)
        if args.aggregate_path:
            write_live_agency_report(result=result, report_path=args.aggregate_path)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
        print(render_live_agency_status_marker(result), file=sys.stderr)
        return 0 if result.get("ok") else 1
    if not args.transcript_path:
        print(json.dumps({"format_version": LIVE_AGENCY_REPORT_VERSION, "ok": False, "error": "transcript_path_required"}, indent=2, sort_keys=True))
        return 2
    result = read_live_agency_payload(args.transcript_path)
    if args.summary_path:
        write_live_agency_report(result=result, report_path=args.summary_path)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_live_agency_status_marker(result), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
