"""Phase 13.72 — stateful interactive CLI campaign wrapper.

This wrapper keeps the existing ``interactive_cli_campaign.py`` runner unchanged while
providing an opt-in command path that installs the Phase 13.71 live-state hook.
The hook carries the interactive CLI state bundle across turns and writes one
checksum-backed checkpoint JSON file per turn.
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

from app.rpg.interactive_cli_live_state import make_live_interactive_state_hook  # noqa: E402
from tests.rpg import interactive_cli_campaign as cli  # noqa: E402

STATEFUL_INTERACTIVE_CLI_VERSION = "interactive_cli_campaign_state_v1"
DEFAULT_CHECKPOINT_DIRNAME = "interactive-state-checkpoints"
MANIFEST_FILENAME = "interactive-state-checkpoints-manifest.json"


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def default_checkpoint_dir(output_dir: Path) -> Path:
    """Return the default live-state checkpoint directory for a CLI output dir."""

    return output_dir / DEFAULT_CHECKPOINT_DIRNAME


def write_checkpoint_manifest(*, output_dir: Path, checkpoint_paths: Sequence[str | Path]) -> Path:
    """Write a deterministic manifest for state checkpoint files created by the hook."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [Path(path) for path in checkpoint_paths]
    manifest = {
        "format_version": STATEFUL_INTERACTIVE_CLI_VERSION,
        "checkpoint_dir": str(default_checkpoint_dir(output_dir)),
        "checkpoint_count": len(paths),
        "checkpoints": [path.name for path in paths],
    }
    manifest_path = output_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return manifest_path


def run_stateful_interactive_campaign(
    *,
    turns: int,
    session_id: str,
    output_dir: Path,
    scripted_commands: Sequence[str] | None = None,
    reset_session: bool = True,
    console_llm: bool = True,
    include_raw_result: bool = True,
    artifact_detail: str = "debug",
    enable_llm_intent_fallback: bool = True,
    seed_live_survival: bool = False,
    checkpoint_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the live CLI campaign with carried state bundles/checkpoint files enabled."""

    output_dir = Path(output_dir)
    resolved_checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else default_checkpoint_dir(output_dir)
    hook = make_live_interactive_state_hook(checkpoint_dir=resolved_checkpoint_dir)
    result = cli.run_interactive_campaign(
        turns=turns,
        session_id=session_id,
        output_dir=output_dir,
        scripted_commands=scripted_commands,
        reset_session=reset_session,
        console_llm=console_llm,
        include_raw_result=include_raw_result,
        artifact_detail=artifact_detail,
        enable_llm_intent_fallback=enable_llm_intent_fallback,
        seed_live_survival=seed_live_survival,
        after_turn_hook=hook,
    )
    manifest_path = write_checkpoint_manifest(output_dir=output_dir, checkpoint_paths=hook.saved_checkpoint_paths)
    summary = dict(result.get("summary") or {})
    summary["stateful_interactive_cli"] = {
        "format_version": STATEFUL_INTERACTIVE_CLI_VERSION,
        "checkpoint_dir": str(resolved_checkpoint_dir),
        "checkpoint_count": len(hook.saved_checkpoint_paths),
        "checkpoint_manifest_path": str(manifest_path),
    }
    result["summary"] = summary
    result["stateful_interactive_cli"] = summary["stateful_interactive_cli"]
    result["interactive_cli_state_checkpoint_paths"] = list(hook.saved_checkpoint_paths)
    artifacts = dict(result.get("artifacts") or {})
    artifacts["state_checkpoint_manifest_path"] = str(manifest_path)
    artifacts["state_checkpoint_dir"] = str(resolved_checkpoint_dir)
    result["artifacts"] = artifacts
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an interactive command-line RPG campaign with carried state checkpoints.")
    parser.add_argument("--turns", type=int, default=30, help="Expected/target number of player turns. Default: 30.")
    parser.add_argument("--session-id", default="", help="Optional session id. Defaults to interactive_cli_<run>.")
    parser.add_argument("--run-id", default="", help="Optional run id for artifact folder naming.")
    parser.add_argument("--output-dir", default="", help="Optional output directory. Defaults under resources/data/test-results.")
    parser.add_argument("--script-file", default="", help="Optional newline-delimited player commands for non-interactive smoke runs.")
    parser.add_argument("--checkpoint-dir", default="", help="Optional state checkpoint directory. Defaults under the output directory.")
    parser.add_argument("--no-reset-session-state", action="store_true", help="Do not delete saved session files before starting.")
    parser.add_argument("--no-console-llm", action="store_true", help="Do not print manual LLM console diagnostics per turn.")
    parser.add_argument("--no-llm-intent-fallback", action="store_true", help="Disable central-provider fallback intent classification for ambiguous service/commerce requests.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed the interactive session with starter survival needs, items, and currency.")
    parser.add_argument("--summary-only", action="store_true", help="Store compact turn summaries instead of raw result payloads.")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run_id = _safe_str(args.run_id).strip() or cli.default_run_id()
    output_dir = Path(args.output_dir) if args.output_dir else cli.default_output_dir(run_id)
    session_id = _safe_str(args.session_id).strip() or f"interactive_cli_{run_id}"
    commands = cli.read_scripted_commands(args.script_file) if args.script_file else None
    result = run_stateful_interactive_campaign(
        turns=int(args.turns),
        session_id=session_id,
        output_dir=output_dir,
        scripted_commands=commands,
        reset_session=not bool(args.no_reset_session_state),
        console_llm=not bool(args.no_console_llm),
        include_raw_result=not bool(args.summary_only),
        artifact_detail=args.artifact_detail,
        enable_llm_intent_fallback=not bool(args.no_llm_intent_fallback),
        seed_live_survival=not bool(args.no_live_survival_seed),
        checkpoint_dir=Path(args.checkpoint_dir) if args.checkpoint_dir else None,
    )
    print(json.dumps(result.get("stateful_interactive_cli") or {}, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
