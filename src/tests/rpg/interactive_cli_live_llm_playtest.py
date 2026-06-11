"""Phase 13.97 — opt-in live LLM RPG playtest runner with quality evaluation.

This module intentionally does not run in normal deterministic CI unless the caller
explicitly opts in.  It drives the existing interactive CLI campaign with scripted
commands, then evaluates the generated transcript with the deterministic live
quality evaluator from Phase 13.94.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

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

LIVE_LLM_PLAYTEST_VERSION = "rpg_live_llm_playtest_v1"
LIVE_LLM_PLAYTEST_STATUS_MARKER = "RPG_LIVE_LLM_PLAYTEST"
LIVE_LLM_PLAYTEST_ENV_FLAG = "RPG_RUN_LIVE_LLM_PLAYTEST"
DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS = (
    "Bran, remember this: my trail name is Ash Lantern.",
    "I ask Bran what trouble he has heard on the road.",
    "I buy two rations for the trail.",
    "I head north toward the old road and watch for bandits.",
    "I ask what choice I should make next.",
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_run_id() -> str:
    return f"live_llm_playtest_{uuid.uuid4().hex[:8]}"


def _default_output_dir(run_id: str) -> Path:
    return cli.DEFAULT_OUTPUT_ROOT / f"interactive-cli-live-llm-playtest-{run_id}"


def _load_commands(*, script_file: str | Path | None = None, commands: Sequence[str] | None = None) -> list[str]:
    if script_file:
        return cli.read_scripted_commands(script_file)
    explicit = [_safe_str(command).strip() for command in commands or [] if _safe_str(command).strip()]
    return explicit or list(DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS)


def render_live_llm_playtest_status_marker(result: Mapping[str, Any]) -> str:
    """Render a one-line marker for scraping live playtest logs."""

    quality = _safe_dict(result.get("quality"))
    ok = "true" if bool(result.get("ok")) else "false"
    skipped = "true" if bool(result.get("skipped")) else "false"
    turn_count = int(quality.get("turn_count") or result.get("turn_count") or 0)
    avg_score = float(quality.get("avg_score") or 0.0)
    fun_score = float(_safe_dict(quality.get("scores")).get("fun") or 0.0)
    quality_failures = quality.get("failures") if isinstance(quality.get("failures"), list) else []
    error = _safe_str(
        result.get("error")
        or quality.get("error")
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
    allow_live: bool = False,
    reset_session: bool = True,
    console_llm: bool = False,
    seed_live_survival: bool = True,
    artifact_detail: str = "debug",
    summary_path: str | Path | None = None,
    campaign_runner: Any | None = None,
) -> dict[str, Any]:
    """Run an opt-in scripted live LLM playtest and evaluate its transcript."""

    if not allow_live and not _truthy_env(LIVE_LLM_PLAYTEST_ENV_FLAG):
        return {
            "format_version": LIVE_LLM_PLAYTEST_VERSION,
            "ok": False,
            "skipped": True,
            "error": "live_llm_playtest_not_enabled",
            "required_env": LIVE_LLM_PLAYTEST_ENV_FLAG,
        }

    resolved_run_id = _safe_str(run_id).strip() or _default_run_id()
    resolved_session_id = _safe_str(session_id).strip() or f"interactive_cli_{resolved_run_id}"
    resolved_output_dir = Path(output_dir) if output_dir else _default_output_dir(resolved_run_id)
    scripted_commands = _load_commands(script_file=script_file, commands=commands)
    resolved_turns = int(turns or len(scripted_commands) or len(DEFAULT_LIVE_LLM_PLAYTEST_COMMANDS))
    runner = campaign_runner or cli.run_interactive_campaign

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
    )
    artifacts = _safe_dict(campaign_result.get("artifacts"))
    transcript_path = Path(_safe_str(artifacts.get("transcript_path")) or (resolved_output_dir / "interactive-transcript.json"))
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
        "commands": scripted_commands,
        "output_dir": str(resolved_output_dir),
        "transcript_path": str(transcript_path),
        "quality_summary_path": str(resolved_summary_path),
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
    parser.add_argument("--allow-live", action="store_true", help=f"Allow live provider execution without setting {LIVE_LLM_PLAYTEST_ENV_FLAG}=1.")
    parser.add_argument("--no-reset-session-state", action="store_true", help="Do not delete saved session files before starting.")
    parser.add_argument("--console-llm", action="store_true", help="Print manual LLM console diagnostics per turn.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival needs/items/currency.")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    parser.add_argument("--summary-path", default="", help="Optional path to persist the live-quality summary JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_live_llm_playtest(
        turns=int(args.turns or 0) or None,
        session_id=args.session_id,
        run_id=args.run_id,
        output_dir=args.output_dir or None,
        commands=args.command,
        script_file=args.script_file or None,
        allow_live=bool(args.allow_live),
        reset_session=not bool(args.no_reset_session_state),
        console_llm=bool(args.console_llm),
        seed_live_survival=not bool(args.no_live_survival_seed),
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
