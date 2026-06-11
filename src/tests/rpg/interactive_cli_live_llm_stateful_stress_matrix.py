"""Phase 14.11 — opt-in stateful live LLM stress matrix."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
for path in (str(THIS_FILE.parents[1]), str(THIS_FILE.parents[2]), str(THIS_FILE.parents[3])):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg.interactive_cli_live_llm_playtest import LIVE_LLM_PLAYTEST_ENV_FLAG, run_live_llm_playtest  # noqa: E402
from tests.rpg.interactive_cli_live_quality_eval import (  # noqa: E402
    aggregate_live_quality_eval_summary_files,
    write_live_quality_aggregate_summary,
    write_live_quality_eval_summary,
)

LIVE_STATEFUL_STRESS_MATRIX_VERSION = "rpg_live_stateful_stress_matrix_v1"
LIVE_STATEFUL_STRESS_SEMANTIC_VERSION = "rpg_live_stateful_stress_semantics_v1"
LIVE_STATEFUL_STRESS_STATUS_MARKER = "RPG_LIVE_STATEFUL_STRESS_MATRIX"
DEFAULT_LIVE_STATEFUL_STRESS_DIR = Path("resources") / "data" / "test-results" / "live-llm-stateful-stress-matrix"

LIVE_STATEFUL_STRESS_PACKS: dict[str, tuple[str, ...]] = {
    "companion-memory-travel": (
        "I ask Bran to travel with me as a companion for the north road.",
        "I tell Bran to remember this warning phrase: red lantern.",
        "I leave the Rusty Flagon with Bran and head toward the old road.",
        "I ask Bran what warning phrase I gave him before we left.",
    ),
    "commerce-rest-ledger": (
        "I ask Bran the exact room price and whether supper is included.",
        "I rent the room and pay the price if I can afford it.",
        "I check my coin after paying and note what changed.",
        "I rest for the night and ask what changed after resting.",
    ),
    "investigation-combat-aftermath": (
        "I ask for the best clue about the bandit trail and who saw it.",
        "I follow the tracks until I confront the threat.",
        "I defend myself and resolve the fight without ignoring injuries.",
        "I check what objective, wound, reward, or danger changed after the fight.",
    ),
    "travel-return-continuity": (
        "I leave the Rusty Flagon and choose the north road.",
        "I remember the most useful landmark on the way out.",
        "I continue until the path forks or reaches a shelter.",
        "I ask where I am, how I got here, and how I could return.",
    ),
}

LIVE_STATEFUL_STRESS_REQUIREMENTS: dict[str, dict[str, dict[str, Any]]] = {
    "companion-memory-travel": {
        "companion_present": {"prompt": "Show Bran is travelling with, accompanying, or present with the player as a companion.", "phrases": ("bran", "companion", "accompany", "travel with", "with you", "joins")},
        "seeded_memory_recalled": {"prompt": "Show recall of the seeded warning phrase red lantern or a clearly remembered warning phrase.", "phrases": ("red lantern", "warning phrase", "remember", "recalled")},
        "travel_continuity": {"prompt": "Connect the tavern departure to road travel or the old/north road.", "phrases": ("road", "north", "old road", "left the rusty flagon", "travel")},
    },
    "commerce-rest-ledger": {
        "service_price": {"prompt": "Show a concrete inn service price, room cost, or included service detail.", "phrases": ("price", "room", "silver", "cost", "supper")},
        "payment_or_ledger": {"prompt": "Show payment, coin, affordability, or a before/after ledger consequence.", "phrases": ("pay", "paid", "coin", "silver", "afford", "after paying", "changed")},
        "rest_consequence": {"prompt": "Show that resting changed or affected the player, time, safety, fatigue, or recovery.", "phrases": ("rest", "resting", "night", "recovered", "fatigue", "changed")},
    },
    "investigation-combat-aftermath": {
        "investigation_to_threat": {"prompt": "Connect a clue, witness, tracks, or trail to reaching the threat.", "phrases": ("clue", "witness", "tracks", "trail", "threat", "bandit")},
        "combat_resolved": {"prompt": "Show the fight or threat was resolved, not merely foreshadowed.", "phrases": ("fight", "resolved", "over", "defend", "strike", "threat", "bandit")},
        "aftermath_changed": {"prompt": "Show an aftermath state change such as wound, injury, reward, objective, danger, or cost.", "phrases": ("wound", "injury", "reward", "objective", "danger", "cost", "changed")},
    },
    "travel-return-continuity": {
        "origin_and_departure": {"prompt": "Establish leaving the Rusty Flagon or tavern as the origin.", "phrases": ("rusty flagon", "tavern", "leave", "left")},
        "landmark_or_fork": {"prompt": "Identify a landmark, fork, shelter, or path feature during travel.", "phrases": ("landmark", "fork", "shelter", "path", "road")},
        "return_route": {"prompt": "Explain current location, route continuity, or how the player could return.", "phrases": ("where", "return", "back", "route", "path", "how you got")},
    },
}


def _s(value: Any) -> str: return "" if value is None else str(value)
def _d(value: Any) -> dict[str, Any]: return dict(value) if isinstance(value, Mapping) else {}
def _l(value: Any) -> list[Any]: return list(value) if isinstance(value, list) else []


def _slug(value: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in _s(value).strip().lower()).strip("-")
    while "--" in slug: slug = slug.replace("--", "-")
    return slug or "stress-pack"


def _read_json(path: Path) -> dict[str, Any]:
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def list_live_stateful_stress_packs() -> dict[str, list[str]]:
    return {name: list(commands) for name, commands in sorted(LIVE_STATEFUL_STRESS_PACKS.items())}


def resolve_live_stateful_stress_packs(packs: Sequence[str] | None = None) -> list[str]:
    selected = [_s(pack).strip() for pack in packs or [] if _s(pack).strip()]
    if not selected: return sorted(LIVE_STATEFUL_STRESS_PACKS)
    unknown = sorted(pack for pack in selected if pack not in LIVE_STATEFUL_STRESS_PACKS)
    if unknown:
        raise ValueError(f"unknown_live_stateful_stress_pack:{','.join(unknown)};available={','.join(sorted(LIVE_STATEFUL_STRESS_PACKS))}")
    result: list[str] = []
    for pack in selected:
        if pack not in result: result.append(pack)
    return result


def _turns(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    turns = payload.get("turns")
    if isinstance(turns, list): return [_d(turn) for turn in turns]
    turns = _d(payload.get("transcript")).get("turns")
    return [_d(turn) for turn in turns] if isinstance(turns, list) else []


def _turn_text(turn: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for source in (turn, _d(turn.get("raw_result") or turn.get("result")), _d(turn.get("structured_narration"))):
        for key in ("player_input", "raw_narration", "narration", "visible_response", "final_narration", "response", "text", "summary"):
            value = _s(source.get(key)).strip()
            if value: parts.append(value)
    return "\n".join(parts)


def _context(payload: Mapping[str, Any], *, pack: str) -> dict[str, Any]:
    return {
        "format_version": "rpg_live_stateful_stress_judge_context_v1",
        "scenario_pack": pack,
        "commands": list(LIVE_STATEFUL_STRESS_PACKS.get(pack, ())),
        "requirements": {name: _s(spec.get("prompt")) for name, spec in sorted(LIVE_STATEFUL_STRESS_REQUIREMENTS.get(pack, {}).items())},
        "turns": [
            {"turn_index": turn.get("turn_index"), "player_input": _s(turn.get("player_input")), "visible_text": _turn_text(turn)[:1200], "narration_source": _s(turn.get("narration_source"))}
            for turn in _turns(payload) if _turn_text(turn).strip()
        ],
    }


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping): return dict(value)
    text = _s(value).strip()
    if not text: return {}
    try:
        payload = json.loads(text)
        return dict(payload) if isinstance(payload, Mapping) else {}
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start:end + 1])
                return dict(payload) if isinstance(payload, Mapping) else {}
            except json.JSONDecodeError: return {}
    return {}


def _generate_judge(*, transcript_or_result: Mapping[str, Any], pack: str, timeout_s: float = 45.0) -> dict[str, Any]:
    try:
        from app.rpg.llm_app_gateway import build_app_llm_gateway
        gateway = build_app_llm_gateway()
    except Exception as exc:
        raise RuntimeError(f"stateful_stress_judge_gateway_unavailable:{type(exc).__name__}:{exc}") from exc
    prompt = (
        "Judge whether this live RPG transcript visibly satisfies each stateful stress requirement. "
        "Use only the provided transcript and commands. Return strict JSON only with shape: "
        '{"ok": boolean, "requirements": {"<requirement>": {"ok": boolean, "evidence": string, "reason": string}}, "reason": string}. '
        "Require visible continuity or consequence; do not reward generic prose."
    )
    return _json_obj(gateway.generate(prompt, context=_context(transcript_or_result, pack=pack), timeout_s=timeout_s))


def _normalize_judge(raw: Any, *, pack: str) -> tuple[dict[str, Any], str]:
    payload, reqs = _json_obj(raw), LIVE_STATEFUL_STRESS_REQUIREMENTS.get(pack, {})
    judged = _d(payload.get("requirements"))
    if not payload or not reqs: return {}, "empty_judge_payload"
    if not judged: return {}, "missing_requirements"
    matched: dict[str, dict[str, Any]] = {}; failures: list[str] = []
    for requirement, spec in sorted(reqs.items()):
        item = _d(judged.get(requirement))
        if "ok" not in item: return {}, f"missing_requirement:{requirement}"
        ok = bool(item.get("ok"))
        matched[requirement] = {"ok": ok, "evidence": _s(item.get("evidence"))[:500], "reason": _s(item.get("reason"))[:500], "accepted_phrases": list(_l(list(spec.get("phrases") or ())))}
        if not ok: failures.append(f"stateful_semantic_{pack.replace('-', '_')}_{requirement}_missing")
    return ({"format_version": LIVE_STATEFUL_STRESS_SEMANTIC_VERSION, "ok": not failures, "scenario_pack": pack, "requirement_count": len(reqs), "missing_count": len(failures), "failures": failures, "warnings": [], "matched": matched, "judge": {"mode": "llm_judge", "used": True, "valid": True, "ok": not failures, "reason": _s(payload.get("reason"))[:500]}}, "")


def _deterministic(payload: Mapping[str, Any], *, pack: str) -> dict[str, Any]:
    text = "\n".join(_turn_text(turn) for turn in _turns(payload)).lower()
    reqs = LIVE_STATEFUL_STRESS_REQUIREMENTS.get(pack, {})
    matched: dict[str, dict[str, Any]] = {}; failures: list[str] = []
    for requirement, spec in sorted(reqs.items()):
        phrases = tuple(_s(item).lower() for item in _l(list(spec.get("phrases") or ())))
        phrase = next((item for item in phrases if item and item in text), "")
        matched[requirement] = {"ok": bool(phrase), "evidence": phrase, "reason": "deterministic_phrase_match" if phrase else "no_accepted_phrase_found", "accepted_phrases": list(phrases)}
        if not phrase: failures.append(f"stateful_semantic_{pack.replace('-', '_')}_{requirement}_missing")
    return {"format_version": LIVE_STATEFUL_STRESS_SEMANTIC_VERSION, "ok": not failures, "scenario_pack": pack, "requirement_count": len(reqs), "missing_count": len(failures), "failures": failures, "warnings": [], "matched": matched, "judge": {"mode": "deterministic_fallback", "used": False, "valid": False, "error": "llm_judge_not_attempted"}}


def evaluate_live_stateful_stress_semantics(payload: Mapping[str, Any], *, pack: str, semantic_judge_func: Callable[..., Any] | None = None, use_llm_judge: bool = True) -> dict[str, Any]:
    pack = _s(pack).strip()
    if pack not in LIVE_STATEFUL_STRESS_REQUIREMENTS:
        return {"format_version": LIVE_STATEFUL_STRESS_SEMANTIC_VERSION, "ok": True, "scenario_pack": pack, "requirement_count": 0, "missing_count": 0, "failures": [], "warnings": [], "matched": {}, "judge": {"mode": "none", "used": False, "valid": False, "error": "no_pack_requirements"}}
    judge_error = ""
    if use_llm_judge:
        try:
            raw = semantic_judge_func(transcript_or_result=payload, pack=pack, context=_context(payload, pack=pack), requirements=LIVE_STATEFUL_STRESS_REQUIREMENTS[pack]) if semantic_judge_func else _generate_judge(transcript_or_result=payload, pack=pack)
            judged, judge_error = _normalize_judge(raw, pack=pack)
            if judged: return judged
        except Exception as exc:
            judge_error = f"{type(exc).__name__}:{exc}"
    fallback = _deterministic(payload, pack=pack)
    fallback["judge"] = {"mode": "deterministic_fallback", "used": bool(use_llm_judge), "valid": False, "error": judge_error or "llm_judge_disabled"}
    if use_llm_judge: fallback["warnings"] = sorted(set(_l(fallback.get("warnings")) + ["stateful_semantic_llm_judge_fallback_used"]))
    return fallback


def apply_stateful_stress_semantics_to_quality(quality: Mapping[str, Any], semantics: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(quality)
    result["failures"] = sorted(set(_l(result.get("failures")) + _l(semantics.get("failures"))))
    result["warnings"] = sorted(set(_l(result.get("warnings")) + _l(semantics.get("warnings"))))[:100]
    result["stateful_stress_semantics"] = dict(semantics)
    signals = _d(result.get("signals")); judge = _d(semantics.get("judge"))
    signals.update({"stateful_stress_requirement_count": int(semantics.get("requirement_count") or 0), "stateful_stress_missing_count": int(semantics.get("missing_count") or 0), "stateful_stress_judge_mode": _s(judge.get("mode")), "stateful_stress_judge_used": bool(judge.get("used")), "stateful_stress_judge_valid": bool(judge.get("valid"))})
    result["signals"] = signals
    result["ok"] = bool(result.get("ok")) and bool(semantics.get("ok"))
    return result


def _mark_incomplete(aggregate: Mapping[str, Any], *, expected: int, missing: int, errors: Sequence[str]) -> dict[str, Any]:
    result = dict(aggregate); result["expected_summary_count"] = expected; result["missing_summary_count"] = max(0, int(missing or 0))
    error_types = sorted(_s(item) for item in errors if _s(item))
    if result["missing_summary_count"] or error_types:
        failure_types = set(_l(result.get("failure_types"))) | set(error_types)
        if result["missing_summary_count"]: failure_types.add("live_stateful_stress_missing_summaries")
        result.update({"ok": False, "failed": int(result.get("failed") or 0) + result["missing_summary_count"], "failure_count": int(result.get("failure_count") or 0) + result["missing_summary_count"], "failure_types": sorted(failure_types)[:100]})
    return result


def run_live_stateful_stress_matrix(*, packs: Sequence[str] | None = None, allow_live: bool = False, output_dir: str | Path | None = None, run_id_prefix: str = "stateful-stress", session_id_prefix: str = "interactive_cli_stateful_stress", reset_session: bool = True, console_llm: bool = False, seed_live_survival: bool = True, artifact_detail: str = "debug", aggregate_path: str | Path | None = None, playtest_runner: Any | None = None, semantic_judge_func: Callable[..., Any] | None = None, use_llm_judge: bool = True) -> dict[str, Any]:
    try: selected = resolve_live_stateful_stress_packs(packs)
    except ValueError as exc: return {"format_version": LIVE_STATEFUL_STRESS_MATRIX_VERSION, "ok": False, "skipped": False, "error": str(exc)}
    out = Path(output_dir) if output_dir else DEFAULT_LIVE_STATEFUL_STRESS_DIR; out.mkdir(parents=True, exist_ok=True)
    aggregate_file = Path(aggregate_path) if aggregate_path else out / "live-quality-aggregate.json"
    if aggregate_file.exists(): aggregate_file.unlink()
    runner = playtest_runner or run_live_llm_playtest
    runs: list[dict[str, Any]] = []; summary_paths: list[Path] = []
    for index, pack in enumerate(selected, start=1):
        pack_dir = out / f"{index:02d}-{_slug(pack)}"; summary_path = pack_dir / "live-quality-summary.json"
        try:
            result = _d(runner(commands=list(LIVE_STATEFUL_STRESS_PACKS[pack]), scenario_pack="", turns=len(LIVE_STATEFUL_STRESS_PACKS[pack]), session_id=f"{session_id_prefix}_{_slug(pack)}", run_id=f"{run_id_prefix}-{_slug(pack)}", output_dir=pack_dir, allow_live=allow_live, reset_session=reset_session, console_llm=console_llm, seed_live_survival=seed_live_survival, artifact_detail=artifact_detail, summary_path=summary_path, use_llm_semantic_judge=False))
            transcript = _read_json(Path(_s(result.get("transcript_path") or (pack_dir / "interactive-transcript.json"))))
            quality = _read_json(summary_path) or _d(result.get("quality"))
            semantics = evaluate_live_stateful_stress_semantics(transcript or result, pack=pack, semantic_judge_func=semantic_judge_func, use_llm_judge=use_llm_judge)
            quality = apply_stateful_stress_semantics_to_quality(quality, semantics)
            write_live_quality_eval_summary(result=quality, summary_path=summary_path)
            result["ok"] = bool(quality.get("ok")); result["stateful_stress_semantics"] = semantics
        except Exception as exc:
            result = {"ok": False, "skipped": False, "error": f"live_stateful_stress_pack_exception:{type(exc).__name__}", "exception_type": type(exc).__name__, "exception": _s(exc)[:500]}
        runs.append({"scenario_pack": pack, "ok": bool(result.get("ok")), "skipped": bool(result.get("skipped")), "output_dir": str(pack_dir), "quality_summary_path": str(summary_path), "error": _s(result.get("error") or "none")})
        if summary_path.exists(): summary_paths.append(summary_path)
    errors = sorted(_s(run.get("error")) for run in runs if _s(run.get("error")) not in {"", "none"})
    missing = len(selected) - len(summary_paths)
    aggregate = _mark_incomplete(aggregate_live_quality_eval_summary_files(summary_paths), expected=len(selected), missing=missing, errors=errors)
    write_live_quality_aggregate_summary(result=aggregate, aggregate_path=aggregate_file)
    result = {"format_version": LIVE_STATEFUL_STRESS_MATRIX_VERSION, "ok": bool(aggregate.get("ok")) and missing == 0 and not errors, "skipped": bool(runs) and all(run.get("skipped") for run in runs), "pack_count": len(selected), "packs": selected, "output_dir": str(out), "aggregate_path": str(aggregate_file), "summary_paths": [str(path) for path in summary_paths], "runs": runs, "aggregate": aggregate}
    if missing: result.update({"ok": False, "missing_summary_count": missing, "error": next((run.get("error") for run in runs if run.get("error") != "none"), "live_stateful_stress_missing_summaries")})
    elif errors: result.update({"ok": False, "error": errors[0]})
    return result


def render_live_stateful_stress_status_marker(result: Mapping[str, Any]) -> str:
    aggregate = _d(result.get("aggregate")); failure_types = _l(aggregate.get("failure_types"))
    error = _s(result.get("error") or aggregate.get("error") or (failure_types[0] if failure_types else "none"))
    return f"[{LIVE_STATEFUL_STRESS_STATUS_MARKER}] ok={'true' if result.get('ok') else 'false'} skipped={'true' if result.get('skipped') else 'false'} pack_count={int(result.get('pack_count') or 0)} passed={int(aggregate.get('passed') or 0)} failed={int(aggregate.get('failed') or 0)} avg_score={float(aggregate.get('avg_score') or 0.0):.3f} error={error}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run opt-in stateful live LLM stress packs and aggregate transcript quality.")
    parser.add_argument("--pack", action="append", default=[], choices=sorted(LIVE_STATEFUL_STRESS_PACKS), help="Stateful stress pack to run; may be repeated. Defaults to all packs.")
    parser.add_argument("--list-stress-packs", action="store_true")
    parser.add_argument("--allow-live", action="store_true", help=f"Allow live provider execution without setting {LIVE_LLM_PLAYTEST_ENV_FLAG}=1.")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--aggregate-path", default="")
    parser.add_argument("--run-id-prefix", default="stateful-stress")
    parser.add_argument("--session-id-prefix", default="interactive_cli_stateful_stress")
    parser.add_argument("--no-reset-session-state", action="store_true")
    parser.add_argument("--console-llm", action="store_true")
    parser.add_argument("--no-live-survival-seed", action="store_true")
    parser.add_argument("--no-llm-semantic-judge", action="store_true")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.list_stress_packs:
        print(json.dumps({"stress_packs": list_live_stateful_stress_packs()}, indent=2, ensure_ascii=False, sort_keys=True)); return 0
    result = run_live_stateful_stress_matrix(packs=args.pack, allow_live=bool(args.allow_live), output_dir=args.output_dir or None, run_id_prefix=args.run_id_prefix, session_id_prefix=args.session_id_prefix, reset_session=not bool(args.no_reset_session_state), console_llm=bool(args.console_llm), seed_live_survival=not bool(args.no_live_survival_seed), artifact_detail=args.artifact_detail, aggregate_path=args.aggregate_path or None, use_llm_judge=not bool(args.no_llm_semantic_judge))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str)); print(render_live_stateful_stress_status_marker(result), file=sys.stderr)
    if result.get("skipped"): return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
