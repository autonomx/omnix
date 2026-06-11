"""Phase 13.94 — deterministic live RPG transcript quality evaluator.

This helper scores interactive CLI campaign transcripts for player-experience
quality signals without calling an LLM judge.  It is intentionally heuristic and
CI-safe: use it as an early warning layer for boring/repetitive/ungrounded live
runs, then layer optional human or LLM-as-judge review on top later.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

LIVE_QUALITY_EVAL_VERSION = "rpg_live_quality_eval_v1"
LIVE_QUALITY_AGGREGATE_VERSION = "rpg_live_quality_eval_aggregate_v1"
LIVE_QUALITY_STATUS_MARKER = "RPG_LIVE_QUALITY_EVAL"
MIN_ACCEPTABLE_AVG_SCORE = 3.0
MIN_ACCEPTABLE_FUN_SCORE = 2.75
MAX_DUPLICATE_RESPONSE_RATIO = 0.25
MAX_GENERIC_TURN_RATIO = 0.45

GENERIC_PHRASES = (
    "the air is thick",
    "you feel a sense",
    "you can't help but feel",
    "a sense of unease",
    "the room feels tense",
    "shadows dance",
    "the world seems to pause",
    "as you proceed",
    "you notice the atmosphere",
)

ACTION_VERBS = (
    "ask",
    "buy",
    "sell",
    "trade",
    "travel",
    "go",
    "walk",
    "head",
    "attack",
    "fight",
    "draw",
    "block",
    "search",
    "inspect",
    "investigate",
    "remember",
    "tell",
    "join",
    "hire",
    "rest",
    "sleep",
    "eat",
    "drink",
)

HOOK_PHRASES = (
    "you can",
    "will you",
    "do you",
    "next",
    "before you",
    "nearby",
    "rumor",
    "trail",
    "clue",
    "choice",
    "decide",
    "offer",
    "warns",
)

GROUNDING_KEYS = (
    "interactive_cli_state_bundle",
    "interactive_cli_travel_state",
    "interactive_cli_equipment_state",
    "interactive_cli_memory_state",
    "interactive_cli_commerce_state",
    "survival",
    "turn_contract",
)

SPECIFICITY_STOPWORDS = frozenset({"a", "an", "as", "do", "he", "she", "the", "they", "this", "will", "you"})
SCORE_KEYS = ("coherence", "agency", "specificity", "continuity", "fun")


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'-]*", text.lower())


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def _has_specific_detail(text: str) -> bool:
    """Detect concrete named/details while ignoring sentence-start filler words."""

    named_candidates = [match.group(0).lower() for match in re.finditer(r"\b[A-Z][a-z]+\b", text)]
    has_named_detail = any(candidate not in SPECIFICITY_STOPWORDS for candidate in named_candidates)
    has_world_detail = any(
        token in text.lower()
        for token in ("tavern", "road", "market", "inn", "bandit", "bran", "elara", "captain", "gold", "silver", "quest")
    )
    return has_named_detail or has_world_detail


def _extract_turns(transcript_or_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    turns = transcript_or_result.get("turns")
    if isinstance(turns, list):
        return [_safe_dict(turn) for turn in turns]
    transcript = _safe_dict(transcript_or_result.get("transcript"))
    turns = transcript.get("turns")
    if isinstance(turns, list):
        return [_safe_dict(turn) for turn in turns]
    return []


def _extract_narration(turn: Mapping[str, Any]) -> str:
    direct = _safe_str(turn.get("raw_narration") or turn.get("narration") or turn.get("visible_response"))
    if direct:
        return direct
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    for key in ("narration", "response", "visible_response", "text"):
        value = _safe_str(raw.get(key))
        if value:
            return value
    npc = _safe_dict(turn.get("raw_npc") or raw.get("npc"))
    speaker = _safe_str(npc.get("speaker"))
    line = _safe_str(npc.get("line"))
    if speaker or line:
        return f"{speaker}: {line}".strip(": ")
    return ""


def _turn_has_grounding(turn: Mapping[str, Any]) -> bool:
    if any(key in turn for key in GROUNDING_KEYS):
        return True
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    return any(key in raw for key in GROUNDING_KEYS)


def _turn_score(*, player_input: str, narration: str, previous_player_inputs: Sequence[str]) -> dict[str, Any]:
    text = narration.strip()
    words = _words(text)
    player_words = set(_words(player_input))
    narration_words = set(words)
    overlap = len(player_words.intersection(narration_words))
    has_action_reflection = overlap > 0 or _contains_any(text, ACTION_VERBS)
    has_hook = text.endswith("?") or _contains_any(text, HOOK_PHRASES)
    has_specificity = _has_specific_detail(text)
    has_continuity = any(word in text.lower() for prior in previous_player_inputs[-3:] for word in _words(prior) if len(word) >= 5)
    generic = _contains_any(text, GENERIC_PHRASES)
    too_short = len(words) < 8
    too_long = len(words) > 180

    coherence = 4.0
    if not text:
        coherence = 1.0
    elif too_short or too_long:
        coherence -= 1.0
    if generic:
        coherence -= 0.5

    agency = 4.0 if has_action_reflection else 2.0
    specificity = 4.0 if has_specificity else 2.25
    continuity = 4.0 if has_continuity or not previous_player_inputs else 3.0
    fun = 3.25
    if has_hook:
        fun += 0.75
    if has_specificity:
        fun += 0.35
    if generic:
        fun -= 0.75
    if too_short:
        fun -= 0.75

    return {
        "coherence": round(max(1.0, min(5.0, coherence)), 2),
        "agency": round(max(1.0, min(5.0, agency)), 2),
        "specificity": round(max(1.0, min(5.0, specificity)), 2),
        "continuity": round(max(1.0, min(5.0, continuity)), 2),
        "fun": round(max(1.0, min(5.0, fun)), 2),
        "flags": {
            "generic": generic,
            "too_short": too_short,
            "too_long": too_long,
            "has_hook": has_hook,
            "has_action_reflection": has_action_reflection,
            "has_specificity": has_specificity,
            "has_continuity": has_continuity,
        },
    }


def evaluate_live_quality_transcript(transcript_or_result: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate an interactive CLI transcript/result for live-play quality signals."""

    turns = _extract_turns(transcript_or_result)
    per_turn: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []
    previous_inputs: list[str] = []
    normalized_responses: list[str] = []
    generic_turns = 0
    grounded_turns = 0

    for index, turn in enumerate(turns, start=1):
        player_input = _safe_str(turn.get("player_input"))
        narration = _extract_narration(turn)
        score = _turn_score(player_input=player_input, narration=narration, previous_player_inputs=previous_inputs)
        flags = _safe_dict(score.get("flags"))
        if flags.get("generic"):
            generic_turns += 1
            warnings.append(f"turn_{index}_generic_response")
        if flags.get("too_short"):
            warnings.append(f"turn_{index}_response_too_short")
        if flags.get("too_long"):
            warnings.append(f"turn_{index}_response_too_long")
        if not flags.get("has_action_reflection"):
            warnings.append(f"turn_{index}_low_agency_reflection")
        if not narration.strip():
            failures.append(f"turn_{index}_missing_narration")
        if turn.get("error"):
            failures.append(f"turn_{index}_runtime_error")
        if _turn_has_grounding(turn):
            grounded_turns += 1
        normalized_responses.append(" ".join(_words(narration))[:240])
        per_turn.append(
            {
                "turn_index": turn.get("turn_index", index),
                "player_input": player_input,
                "narration_word_count": len(_words(narration)),
                "scores": {key: score[key] for key in SCORE_KEYS},
                "flags": flags,
            }
        )
        if player_input:
            previous_inputs.append(player_input)

    duplicate_count = 0
    seen: set[str] = set()
    for response in normalized_responses:
        if response and response in seen:
            duplicate_count += 1
        seen.add(response)

    turn_count = len(turns)
    duplicate_ratio = round(duplicate_count / turn_count, 4) if turn_count else 0.0
    generic_ratio = round(generic_turns / turn_count, 4) if turn_count else 0.0
    grounding_ratio = round(grounded_turns / turn_count, 4) if turn_count else 0.0

    def avg(metric: str) -> float:
        values = [_safe_dict(item.get("scores")).get(metric) for item in per_turn]
        numbers = [float(value) for value in values if isinstance(value, (int, float))]
        return round(sum(numbers) / len(numbers), 3) if numbers else 0.0

    scores = {metric: avg(metric) for metric in SCORE_KEYS}
    avg_score = round(sum(scores.values()) / len(scores), 3) if scores else 0.0
    if turn_count == 0:
        failures.append("transcript_has_no_turns")
    if duplicate_ratio > MAX_DUPLICATE_RESPONSE_RATIO:
        warnings.append("duplicate_response_ratio_high")
    if generic_ratio > MAX_GENERIC_TURN_RATIO:
        warnings.append("generic_turn_ratio_high")
    if avg_score < MIN_ACCEPTABLE_AVG_SCORE:
        failures.append("average_quality_score_below_threshold")
    if scores.get("fun", 0.0) < MIN_ACCEPTABLE_FUN_SCORE:
        warnings.append("fun_score_below_target")

    return {
        "format_version": LIVE_QUALITY_EVAL_VERSION,
        "ok": not failures,
        "turn_count": turn_count,
        "avg_score": avg_score,
        "scores": scores,
        "thresholds": {
            "min_acceptable_avg_score": MIN_ACCEPTABLE_AVG_SCORE,
            "min_acceptable_fun_score": MIN_ACCEPTABLE_FUN_SCORE,
            "max_duplicate_response_ratio": MAX_DUPLICATE_RESPONSE_RATIO,
            "max_generic_turn_ratio": MAX_GENERIC_TURN_RATIO,
        },
        "signals": {
            "duplicate_response_ratio": duplicate_ratio,
            "duplicate_response_count": duplicate_count,
            "generic_turn_ratio": generic_ratio,
            "generic_turn_count": generic_turns,
            "grounding_ratio": grounding_ratio,
            "grounded_turn_count": grounded_turns,
        },
        "failures": sorted(set(failures)),
        "warnings": sorted(set(warnings))[:100],
        "turns": per_turn,
    }


def read_live_quality_transcript(path: str | Path) -> dict[str, Any]:
    """Read a transcript JSON artifact and evaluate expected bad inputs safely."""

    candidate = Path(path)
    if not candidate.exists():
        return {"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "transcript_missing"}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "transcript_json_invalid"}
    if not isinstance(payload, Mapping):
        return {"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "transcript_payload_not_object"}
    return evaluate_live_quality_transcript(payload)


def write_live_quality_eval_summary(*, result: Mapping[str, Any], summary_path: str | Path) -> Path:
    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return path


def validate_live_quality_eval_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a persisted live-quality summary before aggregation."""

    missing = sorted(key for key in ("format_version", "ok", "turn_count", "avg_score", "scores") if key not in payload)
    if missing:
        return {"ok": False, "error": "live_quality_summary_required_keys_missing", "missing_keys": missing}
    if payload.get("format_version") != LIVE_QUALITY_EVAL_VERSION:
        return {
            "ok": False,
            "error": "live_quality_summary_version_mismatch",
            "expected": LIVE_QUALITY_EVAL_VERSION,
            "actual": payload.get("format_version"),
        }
    if not isinstance(payload.get("ok"), bool):
        return {"ok": False, "error": "live_quality_summary_ok_not_bool", "actual_type": type(payload.get("ok")).__name__}
    if not isinstance(payload.get("turn_count"), int) or payload.get("turn_count", 0) < 0:
        return {"ok": False, "error": "live_quality_summary_turn_count_invalid"}
    if not isinstance(payload.get("avg_score"), (int, float)):
        return {"ok": False, "error": "live_quality_summary_avg_score_invalid"}
    scores = _safe_dict(payload.get("scores"))
    missing_scores = sorted(score for score in SCORE_KEYS if not isinstance(scores.get(score), (int, float)))
    if missing_scores:
        return {"ok": False, "error": "live_quality_summary_scores_invalid", "missing_scores": missing_scores}
    return {"ok": True, "format_version": LIVE_QUALITY_EVAL_VERSION}


def read_live_quality_eval_summary(path: str | Path) -> dict[str, Any]:
    """Read a persisted live-quality summary for aggregate mode without raising on expected bad inputs."""

    candidate = Path(path)
    if not candidate.exists():
        return {"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "live_quality_summary_missing", "source_path": str(candidate)}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "live_quality_summary_json_invalid", "source_path": str(candidate)}
    if not isinstance(payload, Mapping):
        return {"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "live_quality_summary_payload_not_object", "source_path": str(candidate)}
    result = dict(payload)
    result.setdefault("source_path", str(candidate))
    return result


def aggregate_live_quality_eval_summary_files(paths: Sequence[str | Path]) -> dict[str, Any]:
    """Read and aggregate persisted live-quality summary JSON files."""

    return aggregate_live_quality_eval_summaries([read_live_quality_eval_summary(path) for path in paths])


def write_live_quality_aggregate_summary(*, result: Mapping[str, Any], aggregate_path: str | Path) -> Path:
    """Persist an aggregate live-quality summary as deterministic JSON."""

    path = Path(aggregate_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    if payload.get("aggregate_format_version") != LIVE_QUALITY_AGGREGATE_VERSION:
        raise ValueError("live_quality_aggregate_version_mismatch")
    if not isinstance(payload.get("ok"), bool):
        raise ValueError("live_quality_aggregate_ok_not_bool")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return path


def aggregate_live_quality_eval_summaries(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate multiple live-quality summary payloads for nightly/playtest review."""

    entries: list[dict[str, Any]] = []
    valid_summary_count = 0
    invalid_summary_count = 0
    passed = 0
    failed = 0
    total_turn_count = 0
    score_totals = {score: 0.0 for score in SCORE_KEYS}
    score_weights = {score: 0 for score in SCORE_KEYS}
    all_failures: list[str] = []
    all_warnings: list[str] = []

    for index, summary in enumerate(summaries):
        payload = dict(summary)
        validation = validate_live_quality_eval_summary(payload)
        entry: dict[str, Any] = {"index": index, "schema_ok": bool(validation.get("ok"))}
        if payload.get("source_path"):
            entry["source_path"] = _safe_str(payload.get("source_path"))
        if not validation.get("ok"):
            invalid_summary_count += 1
            failed += 1
            entry.update({"quality_ok": False, "error": validation.get("error") or "live_quality_summary_schema_invalid", "validation": validation})
            entries.append(entry)
            continue

        valid_summary_count += 1
        quality_ok = bool(payload.get("ok"))
        if quality_ok:
            passed += 1
        else:
            failed += 1
        turn_count = int(payload.get("turn_count") or 0)
        total_turn_count += turn_count
        scores = _safe_dict(payload.get("scores"))
        for score in SCORE_KEYS:
            value = scores.get(score)
            if isinstance(value, (int, float)):
                score_totals[score] += float(value) * max(turn_count, 1)
                score_weights[score] += max(turn_count, 1)
        failures = sorted(_safe_str(item) for item in _safe_list(payload.get("failures")) if _safe_str(item))
        warnings = sorted(_safe_str(item) for item in _safe_list(payload.get("warnings")) if _safe_str(item))
        all_failures.extend(failures)
        all_warnings.extend(warnings)
        entry.update(
            {
                "quality_ok": quality_ok,
                "turn_count": turn_count,
                "avg_score": round(float(payload.get("avg_score") or 0.0), 3),
                "fun_score": round(float(scores.get("fun") or 0.0), 3),
                "failure_count": len(failures),
                "warning_count": len(warnings),
                "error": _safe_str(payload.get("error") or (failures[0] if failures else "none")),
            }
        )
        entries.append(entry)

    average_scores = {
        score: round(score_totals[score] / score_weights[score], 3) if score_weights[score] else 0.0
        for score in SCORE_KEYS
    }
    aggregate_avg_score = round(sum(average_scores.values()) / len(average_scores), 3) if average_scores else 0.0
    return {
        "aggregate_format_version": LIVE_QUALITY_AGGREGATE_VERSION,
        "ok": failed == 0 and invalid_summary_count == 0,
        "summary_count": len(summaries),
        "valid_summary_count": valid_summary_count,
        "invalid_summary_count": invalid_summary_count,
        "passed": passed,
        "failed": failed,
        "total_turn_count": total_turn_count,
        "avg_score": aggregate_avg_score,
        "scores": average_scores,
        "failure_count": len(all_failures),
        "warning_count": len(all_warnings),
        "failure_types": sorted(set(all_failures))[:100],
        "warning_types": sorted(set(all_warnings))[:100],
        "entries": entries,
    }


def render_live_quality_status_marker(result: Mapping[str, Any]) -> str:
    ok = "true" if bool(result.get("ok")) else "false"
    turn_count = int(result.get("turn_count") or 0)
    avg_score = float(result.get("avg_score") or 0.0)
    fun_score = float(_safe_dict(result.get("scores")).get("fun") or 0.0)
    error = _safe_str(result.get("error") or (result.get("failures") or ["none"])[0] if result.get("failures") else "none")
    return f"[{LIVE_QUALITY_STATUS_MARKER}] ok={ok} turn_count={turn_count} avg_score={avg_score:.3f} fun={fun_score:.3f} error={error}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate live interactive RPG transcript quality without calling an LLM judge.")
    parser.add_argument("transcript_path", nargs="?", help="Path to interactive-transcript.json or compatible JSON payload.")
    parser.add_argument("--summary-path", default="", help="Optional path to persist the quality evaluation JSON.")
    parser.add_argument(
        "--aggregate-summary",
        action="append",
        default=[],
        help="Persisted live-quality summary JSON to include in aggregate mode; may be repeated.",
    )
    parser.add_argument("--aggregate-path", default="", help="Optional path to persist aggregate mode JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.aggregate_summary:
        result = aggregate_live_quality_eval_summary_files(args.aggregate_summary)
        if args.aggregate_path:
            write_live_quality_aggregate_summary(result=result, aggregate_path=args.aggregate_path)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
        return 0 if result.get("ok") else 1
    if not args.transcript_path:
        print(json.dumps({"format_version": LIVE_QUALITY_EVAL_VERSION, "ok": False, "error": "transcript_path_required"}, indent=2, sort_keys=True))
        return 2
    result = read_live_quality_transcript(args.transcript_path)
    if args.summary_path:
        write_live_quality_eval_summary(result=result, summary_path=args.summary_path)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_live_quality_status_marker(result), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
