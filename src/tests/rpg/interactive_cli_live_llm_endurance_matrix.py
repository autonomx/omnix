"""Phase 14.12 — opt-in 25-turn live LLM integrated endurance matrix."""
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

LIVE_ENDURANCE_MATRIX_VERSION = "rpg_live_endurance_matrix_v1"
LIVE_ENDURANCE_SEMANTIC_VERSION = "rpg_live_endurance_semantics_v1"
LIVE_ENDURANCE_STATUS_MARKER = "RPG_LIVE_ENDURANCE_MATRIX"
DEFAULT_LIVE_ENDURANCE_DIR = Path("resources") / "data" / "test-results" / "live-llm-endurance-matrix"

LIVE_ENDURANCE_PACKS: dict[str, tuple[str, ...]] = {
    "companion-quest-economy-25": (
        "I ask Bran to travel with me as a companion for a longer job.",
        "I ask Bran what he needs from me before we leave.",
        "I ask the room price and whether food or rest is included.",
        "I buy or rent what I can afford and check my coin afterward.",
        "I tell Bran to remember this warning phrase: blue candle.",
        "I ask about the bandit clue and who first reported it.",
        "I inspect the tavern for a useful lead before leaving.",
        "I leave the Rusty Flagon with Bran for the north road.",
        "I ask Bran to describe the route so we do not get lost.",
        "I follow the clue toward the old quarry road.",
        "I pause and ask Bran what he remembers about the warning phrase.",
        "I check my supplies and money after the travel.",
        "I ask whether our current objective is still the bandit trail.",
        "I investigate the next landmark for tracks or witnesses.",
        "I ask Bran to compare this clue with what we learned in town.",
        "I decide whether to push on or return for rest.",
        "I return toward the Rusty Flagon with Bran.",
        "I ask Bran how we got here and what path takes us back.",
        "I check whether any coin, rest, or supplies changed since the start.",
        "I ask Bran for the warning phrase again after the trip.",
        "I update the quest objective from the clues we found.",
        "I ask Bran what he thinks we should do next.",
        "I verify Bran is still with me before continuing.",
        "I summarize the companion, money, clue, and route state.",
        "I choose the next step based on Bran's memory and the clue.",
    ),
    "combat-travel-aftermath-25": (
        "I prepare to leave town and ask what danger is on the road.",
        "I check my current health, gear, and supplies before departing.",
        "I leave the Rusty Flagon and take the road toward the quarry.",
        "I look for signs of an ambush or tracks near the roadside.",
        "I ask whether anyone or anything is following me.",
        "I confront the threat if it blocks the road.",
        "I enter combat only if the threat attacks or refuses to stand down.",
        "I defend myself and choose a careful attack.",
        "I check whether the enemy is wounded, fleeing, or still fighting.",
        "I continue the fight until it is resolved.",
        "I check my injuries, stamina, and equipment after the fight.",
        "I search the aftermath for a clue, reward, or cost.",
        "I ask what objective changed because of the combat.",
        "I decide whether to rest, retreat, or press on.",
        "I travel to the nearest safe landmark after the fight.",
        "I ask where I am relative to the Rusty Flagon.",
        "I inspect whether the road is safer or more dangerous now.",
        "I record the aftermath in my journal.",
        "I return toward town if I am hurt or need supplies.",
        "I ask an NPC what they heard about the fight.",
        "I compare their report to what actually happened.",
        "I check if any XP, reward, wound, or objective changed.",
        "I ask what threat remains after the resolved fight.",
        "I summarize the combat result and route continuity.",
        "I choose the next safe action based on the aftermath.",
    ),
    "memory-social-world-25": (
        "I tell Bran a private code phrase: silver owl.",
        "I ask Bran to repeat or acknowledge that he will remember it.",
        "I ask Bran who else in the tavern might know about the bandits.",
        "I speak with another local about rumors without revealing the code phrase.",
        "I ask what the rumor says about road danger.",
        "I leave the tavern and travel to a nearby landmark.",
        "I ask where I am and how far I am from the Rusty Flagon.",
        "I inspect the area for signs connected to the rumor.",
        "I return toward town after checking the landmark.",
        "I ask a guard or local whether anything changed while I was gone.",
        "I ask Bran whether he still remembers the private code phrase.",
        "I ask Bran not to share the code phrase with others.",
        "I ask the other local what they remember about our earlier rumor talk.",
        "I compare Bran's memory with the rumor from the other NPC.",
        "I ask whether the world state or road danger changed.",
        "I rest briefly or wait to see if new rumors appear.",
        "I ask Bran again what phrase proves he remembers me.",
        "I ask the local whether they noticed Bran travelling with me.",
        "I check the current location and route back to the tavern.",
        "I ask what objective follows from the rumor and memory.",
        "I choose whether to warn someone using the code phrase.",
        "I ask Bran to explain why the code phrase matters.",
        "I summarize what Bran remembers, what the local heard, and where I am.",
        "I decide who to trust with the next warning.",
        "I ask for the next action that preserves the secret and advances the rumor lead.",
    ),
}

LIVE_ENDURANCE_REQUIREMENTS: dict[str, dict[str, dict[str, Any]]] = {
    "companion-quest-economy-25": {
        "companion_continuity": {"prompt": "Show Bran remains with, accompanies, advises, or is otherwise present with the player across the longer trip.", "phrases": ("bran", "companion", "accompany", "with you", "travels with")},
        "economy_or_service_consequence": {"prompt": "Show a concrete room, food, rest, coin, payment, supply, or affordability consequence from the service/economy actions.", "phrases": ("coin", "silver", "pay", "paid", "room", "supplies", "afford")},
        "quest_clue_continuity": {"prompt": "Show the bandit clue, witness, tracks, quarry road, or objective remains connected across the trip.", "phrases": ("bandit", "clue", "trail", "tracks", "objective", "quarry")},
        "seeded_memory_recall": {"prompt": "Show Bran recalls the seeded warning phrase blue candle or a clearly related remembered warning phrase later in the run.", "phrases": ("blue candle", "warning phrase", "remember")},
    },
    "combat-travel-aftermath-25": {
        "combat_resolution": {"prompt": "Show the fight/threat reaches an explicit resolved state rather than remaining only implied or foreshadowed.", "phrases": ("fight", "resolved", "defeated", "flee", "wounded", "over")},
        "aftermath_state_change": {"prompt": "Show an aftermath consequence such as wound, injury, reward, XP, objective, danger, cost, or journal update.", "phrases": ("wound", "injury", "reward", "xp", "objective", "danger", "journal")},
        "travel_location_continuity": {"prompt": "Show where the player is relative to road/quarry/tavern and how the route continues or returns after combat.", "phrases": ("road", "quarry", "tavern", "rusty flagon", "return", "route")},
    },
    "memory-social-world-25": {
        "private_memory_recall": {"prompt": "Show Bran remembers the private code phrase silver owl or clearly recalls the private secret later.", "phrases": ("silver owl", "code phrase", "private", "remember")},
        "social_rumor_continuity": {"prompt": "Show a rumor, local, guard, or other NPC social thread persists or changes across scenes.", "phrases": ("rumor", "local", "guard", "heard", "noticed", "npc")},
        "location_world_continuity": {"prompt": "Show location continuity across tavern, landmark, road, return path, or changed world/road danger.", "phrases": ("tavern", "landmark", "road", "return", "where", "danger")},
        "secret_handling": {"prompt": "Show the secret/code phrase is protected, used as a warning, or discussed as something not to share with others.", "phrases": ("secret", "private", "warning", "not share", "trust")},
    },
}


def _s(value: Any) -> str: return "" if value is None else str(value)
def _d(value: Any) -> dict[str, Any]: return dict(value) if isinstance(value, Mapping) else {}
def _l(value: Any) -> list[Any]: return list(value) if isinstance(value, list) else []


def _slug(value: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in _s(value).strip().lower()).strip("-")
    while "--" in slug: slug = slug.replace("--", "-")
    return slug or "endurance-pack"


def _read_json(path: Path) -> dict[str, Any]:
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def list_live_endurance_packs() -> dict[str, list[str]]:
    return {name: list(commands) for name, commands in sorted(LIVE_ENDURANCE_PACKS.items())}


def resolve_live_endurance_packs(packs: Sequence[str] | None = None) -> list[str]:
    selected = [_s(pack).strip() for pack in packs or [] if _s(pack).strip()]
    if not selected: return sorted(LIVE_ENDURANCE_PACKS)
    unknown = sorted(pack for pack in selected if pack not in LIVE_ENDURANCE_PACKS)
    if unknown:
        raise ValueError(f"unknown_live_endurance_pack:{','.join(unknown)};available={','.join(sorted(LIVE_ENDURANCE_PACKS))}")
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
        "format_version": "rpg_live_endurance_judge_context_v1",
        "scenario_pack": pack,
        "commands": list(LIVE_ENDURANCE_PACKS.get(pack, ())),
        "requirements": {name: _s(spec.get("prompt")) for name, spec in sorted(LIVE_ENDURANCE_REQUIREMENTS.get(pack, {}).items())},
        "turns": [
            {"turn_index": turn.get("turn_index"), "player_input": _s(turn.get("player_input")), "visible_text": _turn_text(turn)[:1400], "narration_source": _s(turn.get("narration_source"))}
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


def _generate_judge(*, transcript_or_result: Mapping[str, Any], pack: str, timeout_s: float = 60.0) -> dict[str, Any]:
    try:
        from app.rpg.llm_app_gateway import build_app_llm_gateway
        gateway = build_app_llm_gateway()
    except Exception as exc:
        raise RuntimeError(f"live_endurance_judge_gateway_unavailable:{type(exc).__name__}:{exc}") from exc
    prompt = (
        "Judge whether this 25-turn live RPG transcript visibly satisfies each integrated endurance requirement. "
        "Use only the provided transcript and commands. Return strict JSON only with shape: "
        '{"ok": boolean, "requirements": {"<requirement>": {"ok": boolean, "evidence": string, "reason": string}}, "reason": string}. '
        "Require visible continuity, consequence, and cross-turn state. Do not reward isolated keywords or generic prose."
    )
    return _json_obj(gateway.generate(prompt, context=_context(transcript_or_result, pack=pack), timeout_s=timeout_s))


def _normalize_judge(raw: Any, *, pack: str) -> tuple[dict[str, Any], str]:
    payload, reqs = _json_obj(raw), LIVE_ENDURANCE_REQUIREMENTS.get(pack, {})
    judged = _d(payload.get("requirements"))
    if not payload or not reqs: return {}, "empty_judge_payload"
    if not judged: return {}, "missing_requirements"
    matched: dict[str, dict[str, Any]] = {}; failures: list[str] = []
    for requirement, spec in sorted(reqs.items()):
        item = _d(judged.get(requirement))
        if "ok" not in item: return {}, f"missing_requirement:{requirement}"
        ok = bool(item.get("ok"))
        matched[requirement] = {"ok": ok, "evidence": _s(item.get("evidence"))[:600], "reason": _s(item.get("reason"))[:600], "accepted_phrases": list(_l(list(spec.get("phrases") or ())))}
        if not ok: failures.append(f"endurance_semantic_{pack.replace('-', '_')}_{requirement}_missing")
    return ({"format_version": LIVE_ENDURANCE_SEMANTIC_VERSION, "ok": not failures, "scenario_pack": pack, "requirement_count": len(reqs), "missing_count": len(failures), "failures": failures, "warnings": [], "matched": matched, "judge": {"mode": "llm_judge", "used": True, "valid": True, "ok": not failures, "reason": _s(payload.get("reason"))[:600]}}, "")


def _deterministic(payload: Mapping[str, Any], *, pack: str) -> dict[str, Any]:
    text = "\n".join(_turn_text(turn) for turn in _turns(payload)).lower()
    reqs = LIVE_ENDURANCE_REQUIREMENTS.get(pack, {})
    matched: dict[str, dict[str, Any]] = {}; failures: list[str] = []
    for requirement, spec in sorted(reqs.items()):
        phrases = tuple(_s(item).lower() for item in _l(list(spec.get("phrases") or ())))
        phrase = next((item for item in phrases if item and item in text), "")
        matched[requirement] = {"ok": bool(phrase), "evidence": phrase, "reason": "deterministic_phrase_match" if phrase else "no_accepted_phrase_found", "accepted_phrases": list(phrases)}
        if not phrase: failures.append(f"endurance_semantic_{pack.replace('-', '_')}_{requirement}_missing")
    return {"format_version": LIVE_ENDURANCE_SEMANTIC_VERSION, "ok": not failures, "scenario_pack": pack, "requirement_count": len(reqs), "missing_count": len(failures), "failures": failures, "warnings": [], "matched": matched, "judge": {"mode": "deterministic_fallback", "used": False, "valid": False, "error": "llm_judge_not_attempted"}}


def evaluate_live_endurance_semantics(payload: Mapping[str, Any], *, pack: str, semantic_judge_func: Callable[..., Any] | None = None, use_llm_judge: bool = True) -> dict[str, Any]:
    pack = _s(pack).strip()
    if pack not in LIVE_ENDURANCE_REQUIREMENTS:
        return {"format_version": LIVE_ENDURANCE_SEMANTIC_VERSION, "ok": True, "scenario_pack": pack, "requirement_count": 0, "missing_count": 0, "failures": [], "warnings": [], "matched": {}, "judge": {"mode": "none", "used": False, "valid": False, "error": "no_pack_requirements"}}
    judge_error = ""
    if use_llm_judge:
        try:
            raw = semantic_judge_func(transcript_or_result=payload, pack=pack, context=_context(payload, pack=pack), requirements=LIVE_ENDURANCE_REQUIREMENTS[pack]) if semantic_judge_func else _generate_judge(transcript_or_result=payload, pack=pack)
            judged, judge_error = _normalize_judge(raw, pack=pack)
            if judged: return judged
        except Exception as exc:
            judge_error = f"{type(exc).__name__}:{exc}"
    fallback = _deterministic(payload, pack=pack)
    fallback["judge"] = {"mode": "deterministic_fallback", "used": bool(use_llm_judge), "valid": False, "error": judge_error or "llm_judge_disabled"}
    if use_llm_judge: fallback["warnings"] = sorted(set(_l(fallback.get("warnings")) + ["live_endurance_semantic_llm_judge_fallback_used"]))
    return fallback


def apply_endurance_semantics_to_quality(quality: Mapping[str, Any], semantics: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(quality)
    result["failures"] = sorted(set(_l(result.get("failures")) + _l(semantics.get("failures"))))
    result["warnings"] = sorted(set(_l(result.get("warnings")) + _l(semantics.get("warnings"))))[:100]
    result["live_endurance_semantics"] = dict(semantics)
    signals = _d(result.get("signals")); judge = _d(semantics.get("judge"))
    signals.update({"live_endurance_requirement_count": int(semantics.get("requirement_count") or 0), "live_endurance_missing_count": int(semantics.get("missing_count") or 0), "live_endurance_judge_mode": _s(judge.get("mode")), "live_endurance_judge_used": bool(judge.get("used")), "live_endurance_judge_valid": bool(judge.get("valid"))})
    result["signals"] = signals
    result["ok"] = bool(result.get("ok")) and bool(semantics.get("ok"))
    return result


def _mark_incomplete(aggregate: Mapping[str, Any], *, expected: int, missing: int, errors: Sequence[str]) -> dict[str, Any]:
    result = dict(aggregate); result["expected_summary_count"] = expected; result["missing_summary_count"] = max(0, int(missing or 0))
    error_types = sorted(_s(item) for item in errors if _s(item))
    if result["missing_summary_count"] or error_types:
        failure_types = set(_l(result.get("failure_types"))) | set(error_types)
        if result["missing_summary_count"]: failure_types.add("live_endurance_missing_summaries")
        result.update({"ok": False, "failed": int(result.get("failed") or 0) + result["missing_summary_count"], "failure_count": int(result.get("failure_count") or 0) + result["missing_summary_count"], "failure_types": sorted(failure_types)[:100]})
    return result


def run_live_endurance_matrix(*, packs: Sequence[str] | None = None, allow_live: bool = False, output_dir: str | Path | None = None, run_id_prefix: str = "endurance-25", session_id_prefix: str = "interactive_cli_endurance_25", reset_session: bool = True, console_llm: bool = False, seed_live_survival: bool = True, artifact_detail: str = "debug", aggregate_path: str | Path | None = None, playtest_runner: Any | None = None, semantic_judge_func: Callable[..., Any] | None = None, use_llm_judge: bool = True) -> dict[str, Any]:
    try: selected = resolve_live_endurance_packs(packs)
    except ValueError as exc: return {"format_version": LIVE_ENDURANCE_MATRIX_VERSION, "ok": False, "skipped": False, "error": str(exc)}
    out = Path(output_dir) if output_dir else DEFAULT_LIVE_ENDURANCE_DIR; out.mkdir(parents=True, exist_ok=True)
    aggregate_file = Path(aggregate_path) if aggregate_path else out / "live-quality-aggregate.json"
    if aggregate_file.exists(): aggregate_file.unlink()
    runner = playtest_runner or run_live_llm_playtest
    runs: list[dict[str, Any]] = []; summary_paths: list[Path] = []
    for index, pack in enumerate(selected, start=1):
        commands = list(LIVE_ENDURANCE_PACKS[pack])
        pack_dir = out / f"{index:02d}-{_slug(pack)}"; summary_path = pack_dir / "live-quality-summary.json"
        try:
            result = _d(runner(commands=commands, scenario_pack="", turns=len(commands), session_id=f"{session_id_prefix}_{_slug(pack)}", run_id=f"{run_id_prefix}-{_slug(pack)}", output_dir=pack_dir, allow_live=allow_live, reset_session=reset_session, console_llm=console_llm, seed_live_survival=seed_live_survival, artifact_detail=artifact_detail, summary_path=summary_path, use_llm_semantic_judge=False))
            transcript = _read_json(Path(_s(result.get("transcript_path") or (pack_dir / "interactive-transcript.json"))))
            quality = _read_json(summary_path) or _d(result.get("quality"))
            semantics = evaluate_live_endurance_semantics(transcript or result, pack=pack, semantic_judge_func=semantic_judge_func, use_llm_judge=use_llm_judge)
            quality = apply_endurance_semantics_to_quality(quality, semantics)
            write_live_quality_eval_summary(result=quality, summary_path=summary_path)
            result["ok"] = bool(quality.get("ok")); result["live_endurance_semantics"] = semantics
        except Exception as exc:
            result = {"ok": False, "skipped": False, "error": f"live_endurance_pack_exception:{type(exc).__name__}", "exception_type": type(exc).__name__, "exception": _s(exc)[:500]}
        runs.append({"scenario_pack": pack, "ok": bool(result.get("ok")), "skipped": bool(result.get("skipped")), "turn_count": len(commands), "output_dir": str(pack_dir), "quality_summary_path": str(summary_path), "error": _s(result.get("error") or "none")})
        if summary_path.exists(): summary_paths.append(summary_path)
    errors = sorted(_s(run.get("error")) for run in runs if _s(run.get("error")) not in {"", "none"})
    missing = len(selected) - len(summary_paths)
    aggregate = _mark_incomplete(aggregate_live_quality_eval_summary_files(summary_paths), expected=len(selected), missing=missing, errors=errors)
    write_live_quality_aggregate_summary(result=aggregate, aggregate_path=aggregate_file)
    result = {"format_version": LIVE_ENDURANCE_MATRIX_VERSION, "ok": bool(aggregate.get("ok")) and missing == 0 and not errors, "skipped": bool(runs) and all(run.get("skipped") for run in runs), "pack_count": len(selected), "packs": selected, "output_dir": str(out), "aggregate_path": str(aggregate_file), "summary_paths": [str(path) for path in summary_paths], "runs": runs, "aggregate": aggregate}
    if missing: result.update({"ok": False, "missing_summary_count": missing, "error": next((run.get("error") for run in runs if run.get("error") != "none"), "live_endurance_missing_summaries")})
    elif errors: result.update({"ok": False, "error": errors[0]})
    return result


def render_live_endurance_status_marker(result: Mapping[str, Any]) -> str:
    aggregate = _d(result.get("aggregate")); failure_types = _l(aggregate.get("failure_types"))
    error = _s(result.get("error") or aggregate.get("error") or (failure_types[0] if failure_types else "none"))
    return f"[{LIVE_ENDURANCE_STATUS_MARKER}] ok={'true' if result.get('ok') else 'false'} skipped={'true' if result.get('skipped') else 'false'} pack_count={int(result.get('pack_count') or 0)} passed={int(aggregate.get('passed') or 0)} failed={int(aggregate.get('failed') or 0)} avg_score={float(aggregate.get('avg_score') or 0.0):.3f} error={error}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run opt-in 25-turn integrated live LLM endurance packs and aggregate quality.")
    parser.add_argument("--pack", action="append", default=[], choices=sorted(LIVE_ENDURANCE_PACKS), help="Endurance pack to run; may be repeated. Defaults to all packs.")
    parser.add_argument("--list-endurance-packs", action="store_true")
    parser.add_argument("--allow-live", action="store_true", help=f"Allow live provider execution without setting {LIVE_LLM_PLAYTEST_ENV_FLAG}=1.")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--aggregate-path", default="")
    parser.add_argument("--run-id-prefix", default="endurance-25")
    parser.add_argument("--session-id-prefix", default="interactive_cli_endurance_25")
    parser.add_argument("--no-reset-session-state", action="store_true")
    parser.add_argument("--console-llm", action="store_true")
    parser.add_argument("--no-live-survival-seed", action="store_true")
    parser.add_argument("--no-llm-semantic-judge", action="store_true")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.list_endurance_packs:
        print(json.dumps({"endurance_packs": list_live_endurance_packs()}, indent=2, ensure_ascii=False, sort_keys=True)); return 0
    result = run_live_endurance_matrix(packs=args.pack, allow_live=bool(args.allow_live), output_dir=args.output_dir or None, run_id_prefix=args.run_id_prefix, session_id_prefix=args.session_id_prefix, reset_session=not bool(args.no_reset_session_state), console_llm=bool(args.console_llm), seed_live_survival=not bool(args.no_live_survival_seed), artifact_detail=args.artifact_detail, aggregate_path=args.aggregate_path or None, use_llm_judge=not bool(args.no_llm_semantic_judge))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str)); print(render_live_endurance_status_marker(result), file=sys.stderr)
    if result.get("skipped"): return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
