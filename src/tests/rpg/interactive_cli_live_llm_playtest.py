"""Phase 13.97+ — opt-in live LLM RPG playtest runner with quality evaluation.

The live runner orchestrates scripted packs and scoring only. Deferred narration
completion/provenance is owned by ``interactive_cli_campaign.run_interactive_campaign``
through the shared Phase 14.05 runtime narration contract.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_cli_campaign as cli  # noqa: E402
from tests.rpg.interactive_cli_live_quality_eval import (  # noqa: E402
    evaluate_live_quality_transcript,
    read_live_quality_transcript,
    write_live_quality_eval_summary,
)
from tests.rpg.manual import runtime_narration_contract as narration_contract  # noqa: E402

LIVE_LLM_PLAYTEST_VERSION = "rpg_live_llm_playtest_v1"
LIVE_LLM_PLAYTEST_STATUS_MARKER = "RPG_LIVE_LLM_PLAYTEST"
LIVE_LLM_PLAYTEST_ENV_FLAG = "RPG_RUN_LIVE_LLM_PLAYTEST"
LIVE_DEFERRED_NARRATION_DRAIN_SOURCE = narration_contract.RUNTIME_DEFERRED_NARRATION_DRAIN_SOURCE
LIVE_DEFERRED_NARRATION_CONTEXT_VERSION = narration_contract.RUNTIME_DEFERRED_NARRATION_CONTEXT_VERSION
LIVE_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION = narration_contract.RUNTIME_TRANSCRIPT_PROVENANCE_NORMALIZATION_VERSION
LIVE_DEFERRED_NARRATION_MAX_CONTEXT_CHARS = narration_contract.RUNTIME_DEFERRED_NARRATION_MAX_CONTEXT_CHARS

# Backward-compatible aliases for earlier Phase 14 deterministic tests.  They now
# point at the shared runtime-owned contract helpers.
_grounded_live_narration_context = narration_contract.grounded_runtime_narration_context
_classify_live_deferred_narration_error = narration_contract.classify_runtime_narration_error
drain_deferred_live_narration_turn = narration_contract.drain_deferred_runtime_narration_turn
normalize_deferred_live_narration_transcript_payload = narration_contract.normalize_runtime_narration_transcript_payload
normalize_deferred_live_narration_transcript_file = narration_contract.normalize_runtime_narration_transcript_file

DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS = (
    "Bran, remember this: my trail name is Ash Lantern.",
    "I ask Bran what trouble he has heard on the road.",
    "I buy two rations for the trail.",
    "I head north toward the old road and watch for bandits.",
    "I ask what choice I should make next.",
)
LIVE_LLM_PLAYTEST_SCENARIO_PACKS: dict[str, tuple[str, ...]] = {
    "tavern-memory": (
        "Bran, remember this: my trail name is Ash Lantern.",
        "I ask Bran what trouble he has heard on the road tonight.",
        "I ask Bran what name he should use if he needs to warn me later.",
        "I ask what concrete lead I should follow next.",
    ),
    "commerce-travel": (
        "I ask Elara what trail food she recommends for the north road.",
        "I buy two rations and ask the exact price.",
        "I check my pack and coin before leaving the market.",
        "I head north toward the old road and watch for landmarks.",
        "I ask what choices I have now that I am on the road.",
    ),
    "combat-tension": (
        "I follow the bandit tracks north from the tavern.",
        "I draw my sword and warn the bandit to drop his weapon.",
        "I attack only if the bandit lunges first.",
        "I check whether the fight changed my injuries, gear, or reward.",
        "I ask what danger remains nearby.",
    ),
    "party-companion": (
        "I ask Bran whether he would travel with me for a while.",
        "I ask what help he could offer if he joins my party.",
        "I accept Bran as a companion if he is willing.",
        "I check who is travelling with me now.",
    ),
    "quest-investigation": (
        "I ask Bran for the clearest clue about the bandit trail.",
        "I question the nearest witness about what they saw.",
        "I inspect the muddy tracks for a useful lead.",
        "I ask what objective I should pursue next.",
    ),
    "inn-service-economy": (
        "I ask Bran the exact price for a room tonight.",
        "I rent a room for the night if I can afford it.",
        "I check my coin after paying for the room.",
        "I ask what resting changed for me.",
    ),
    "travel-encounter": (
        "I leave the Rusty Flagon and head toward the north road.",
        "I watch for landmarks as I travel.",
        "I stop when I notice signs of danger or shelter.",
        "I ask where I am and what paths are available now.",
    ),
    "combat-resolution": (
        "I follow the bandit trail until I confront the threat.",
        "I defend myself and strike only when there is an opening.",
        "I check whether the fight is over and what it cost me.",
        "I ask what reward, injury, or objective changed after the fight.",
    ),
    "memory-recall-cross-scene": (
        "Bran, remember this passphrase: blue ember.",
        "I buy a ration and prepare to leave the tavern.",
        "I head toward the old road and then think back to Bran's warning.",
        "I ask Bran or my notes what passphrase I told him earlier.",
    ),
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_run_id() -> str:
    return f"live_llm_playtest_{uuid.uuid4().hex[:8]}"


def _default_output_dir(run_id: str) -> Path:
    return cli.DEFAULT_OUTPUT_ROOT / f"interactive-cli-live-llm-playtest-{run_id}"


def list_live_llm_playtest_scenario_packs() -> dict[str, list[str]]:
    return {name: list(commands) for name, commands in sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS.items())}


def resolve_live_llm_playtest_scenario_pack(name: str) -> list[str]:
    key = _safe_str(name).strip()
    if not key:
        return []
    if key not in LIVE_LLM_PLAYTEST_SCENARIO_PACKS:
        available = ", ".join(sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS))
        raise ValueError(f"unknown_live_llm_playtest_scenario_pack:{key};available={available}")
    return list(LIVE_LLM_PLAYTEST_SCENARIO_PACKS[key])


def _load_commands(
    *,
    script_file: str | Path | None = None,
    commands: Sequence[str] | None = None,
    scenario_pack: str = "",
) -> list[str]:
    if script_file:
        return cli.read_scripted_commands(script_file)
    explicit = [_safe_str(command).strip() for command in commands or [] if _safe_str(command).strip()]
    if explicit:
        return explicit
    packed = resolve_live_llm_playtest_scenario_pack(scenario_pack)
    return packed or list(DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS)


def _empty_contract_summary(enabled: bool) -> dict[str, Any]:
    return narration_contract.new_runtime_narration_contract_summary(enabled=enabled)


def _contract_from_campaign_result(campaign_result: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
    summary = _safe_dict(campaign_result.get("summary"))
    contract = _safe_dict(summary.get("runtime_narration_contract"))
    return contract or _empty_contract_summary(enabled)


def render_live_llm_playtest_status_marker(result: Mapping[str, Any]) -> str:
    quality = _safe_dict(result.get("quality"))
    ok = "true" if bool(result.get("ok")) else "false"
    skipped = "true" if bool(result.get("skipped")) else "false"
    turn_count = int(quality.get("turn_count") or result.get("turn_count") or 0)
    avg_score = float(quality.get("avg_score") or 0.0)
    fun_score = float(_safe_dict(quality.get("scores")).get("fun") or 0.0)
    quality_failures = quality.get("failures") if isinstance(quality.get("failures"), list) else []
    contract = _safe_dict(result.get("runtime_narration_contract"))
    drain = _safe_dict(contract.get("deferred_narration_drain") or result.get("deferred_narration_drain"))
    drain_errors = _safe_list(drain.get("error_types"))
    error = _safe_str(
        result.get("error")
        or quality.get("error")
        or (drain_errors[0] if drain_errors else "")
        or (quality_failures[0] if quality_failures else "none")
    )
    return (
        f"[{LIVE_LLM_PLAYTEST_STATUS_MARKER}] ok={ok} skipped={skipped} "
        f"turn_count={turn_count} avg_score={avg_score:.3f} fun={fun_score:.3f} error={error}"
    )


def run_live_llm_playtest(
    *,
    turns: int | None = None,
    session_id: str = "",
    run_id: str = "",
    output_dir: str | Path | None = None,
    commands: Sequence[str] | None = None,
    script_file: str | Path | None = None,
    scenario_pack: str = "",
    allow_live: bool = False,
    reset_session: bool = True,
    console_llm: bool = False,
    seed_live_survival: bool = True,
    artifact_detail: str = "debug",
    summary_path: str | Path | None = None,
    defer_runtime_narration: bool = True,
    drain_deferred_narration: bool = True,
    deferred_narration_drain_func: Callable[..., Mapping[str, Any] | None] | None = None,
    campaign_runner: Any | None = None,
) -> dict[str, Any]:
    if not allow_live and not _truthy_env(LIVE_LLM_PLAYTEST_ENV_FLAG):
        return {
            "format_version": LIVE_LLM_PLAYTEST_VERSION,
            "ok": False,
            "skipped": True,
            "error": "live_llm_playtest_not_enabled",
            "required_env": LIVE_LLM_PLAYTEST_ENV_FLAG,
        }

    try:
        scripted_commands = _load_commands(script_file=script_file, commands=commands, scenario_pack=scenario_pack)
    except ValueError as exc:
        return {"format_version": LIVE_LLM_PLAYTEST_VERSION, "ok": False, "skipped": False, "error": str(exc)}

    resolved_run_id = _safe_str(run_id).strip() or _default_run_id()
    resolved_session_id = _safe_str(session_id).strip() or f"interactive_cli_{resolved_run_id}"
    resolved_output_dir = Path(output_dir) if output_dir else _default_output_dir(resolved_run_id)
    resolved_turns = int(turns or len(scripted_commands) or len(DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS))
    runner = campaign_runner or cli.run_interactive_campaign
    contract_enabled = bool(defer_runtime_narration and drain_deferred_narration)

    campaign_result = runner(
        turns=resolved_turns,
        session_id=resolved_session_id,
        output_dir=resolved_output_dir,
        scripted_commands=scripted_commands,
        reset_session=reset_session,
        console_llm=console_llm,
        include_raw_result=True,
        artifact_detail=artifact_detail,
        enable_llm_intent_fallback=True,
        seed_live_survival=seed_live_survival,
        defer_runtime_narration=defer_runtime_narration,
        enforce_deferred_narration_contract=contract_enabled,
        deferred_narration_drain_func=deferred_narration_drain_func,
    )
    artifacts = _safe_dict(campaign_result.get("artifacts"))
    transcript_path = Path(_safe_str(artifacts.get("transcript_path")) or (resolved_output_dir / "interactive-transcript.json"))
    runtime_contract = _contract_from_campaign_result(campaign_result, enabled=contract_enabled)
    transcript_normalization = _safe_dict(runtime_contract.get("transcript_provenance_normalization"))
    if transcript_path.exists():
        quality = read_live_quality_transcript(transcript_path)
    else:
        quality = evaluate_live_quality_transcript(campaign_result)
    resolved_summary_path = Path(summary_path) if summary_path else resolved_output_dir / "live-quality-summary.json"
    write_live_quality_eval_summary(result=quality, summary_path=resolved_summary_path)

    result = {
        "format_version": LIVE_LLM_PLAYTEST_VERSION,
        "ok": bool(quality.get("ok")),
        "skipped": False,
        "run_id": resolved_run_id,
        "session_id": resolved_session_id,
        "turn_count": int(quality.get("turn_count") or 0),
        "scenario_pack": _safe_str(scenario_pack).strip(),
        "commands": scripted_commands,
        "output_dir": str(resolved_output_dir),
        "transcript_path": str(transcript_path),
        "quality_summary_path": str(resolved_summary_path),
        "defer_runtime_narration": bool(defer_runtime_narration),
        "drain_deferred_narration": bool(drain_deferred_narration),
        "runtime_narration_contract": runtime_contract,
        "deferred_narration_drain": _safe_dict(runtime_contract.get("deferred_narration_drain")),
        "transcript_provenance_normalization": transcript_normalization,
        "campaign_artifacts": artifacts,
        "quality": quality,
    }
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an opt-in scripted live LLM RPG playtest and evaluate transcript quality.")
    parser.add_argument("--turns", type=int, default=0, help="Number of scripted turns to run; defaults to the command count.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to interactive_cli_<run>.")
    parser.add_argument("--run-id", default="", help="Optional run id for artifact folder naming.")
    parser.add_argument("--output-dir", default="", help="Optional output directory for campaign artifacts.")
    parser.add_argument("--script-file", default="", help="Optional newline-delimited player commands for the live playtest.")
    parser.add_argument("--command", action="append", default=[], help="Scripted player command; may be repeated.")
    parser.add_argument("--scenario-pack", choices=sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS), default="", help="Named built-in live playtest command pack.")
    parser.add_argument("--list-scenario-packs", action="store_true", help="List built-in scenario packs and exit without running a provider.")
    parser.add_argument("--allow-live", action="store_true", help=f"Allow live provider execution without setting {LIVE_LLM_PLAYTEST_ENV_FLAG}=1.")
    parser.add_argument("--no-reset-session-state", action="store_true", help="Do not delete saved session files before starting.")
    parser.add_argument("--console-llm", action="store_true", help="Print manual LLM console diagnostics per turn.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival needs/items/currency.")
    parser.add_argument("--no-deferred-runtime-narration", action="store_true", help="Debug only: do not force deferred post-runtime LLM narration.")
    parser.add_argument("--no-drain-deferred-narration", action="store_true", help="Debug only: score artifacts without enforcing the runtime narration contract.")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    parser.add_argument("--summary-path", default="", help="Optional path to persist the live-quality summary JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.list_scenario_packs:
        print(json.dumps({"scenario_packs": list_live_llm_playtest_scenario_packs()}, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    result = run_live_llm_playtest(
        turns=int(args.turns or 0) or None,
        session_id=args.session_id,
        run_id=args.run_id,
        output_dir=args.output_dir or None,
        commands=args.command,
        script_file=args.script_file or None,
        scenario_pack=args.scenario_pack,
        allow_live=bool(args.allow_live),
        reset_session=not bool(args.no_reset_session_state),
        console_llm=bool(args.console_llm),
        seed_live_survival=not bool(args.no_live_survival_seed),
        defer_runtime_narration=not bool(args.no_deferred_runtime_narration),
        drain_deferred_narration=not bool(args.no_drain_deferred_narration),
        artifact_detail=args.artifact_detail,
        summary_path=args.summary_path or None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_live_llm_playtest_status_marker(result), file=sys.stderr)
    if result.get("skipped"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
