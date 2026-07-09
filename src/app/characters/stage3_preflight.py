"""CLI and public exports for the Character Mode Stage 3 write pilot."""
from __future__ import annotations

import argparse
from pathlib import Path

from .stage3_contracts import (
    Stage3Check,
    Stage3Checkpoint,
    Stage3Metrics,
    Stage3PrepareConfig,
    Stage3Report,
    write_report,
)
from .stage3_http import HttpStage3Gateway, Stage3Gateway
from .stage3_runner import prepare_stage3, verify_stage3_restart


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Omnix Character Mode Stage 3 explicit write-memory pilot."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Run Stage 3 write-memory checks and write a restart checkpoint.",
    )
    prepare.add_argument("--base-url", default=Stage3PrepareConfig().base_url)
    prepare.add_argument("--provider-id", default="lmstudio")
    prepare.add_argument("--model-id", required=True)
    prepare.add_argument("--maya-character-id", default="stage3-maya")
    prepare.add_argument("--alex-character-id", default="stage3-alex")
    prepare.add_argument("--run-id", default="stage3-write-v1")
    prepare.add_argument("--timeout-seconds", type=float, default=120)
    prepare.add_argument("--settle-seconds", type=float, default=8)
    prepare.add_argument("--token-budget", type=int, default=4_000)
    prepare.add_argument(
        "--checkpoint",
        default="resources/data/test-results/character-mode-stage3-checkpoint.json",
    )
    prepare.add_argument(
        "--report",
        default="resources/data/test-results/character-mode-stage3-prepare-report.json",
    )

    verify = subparsers.add_parser(
        "verify-restart",
        help="Verify the Stage 3 write checkpoint after restarting Omnix, then clean up.",
    )
    verify.add_argument(
        "--checkpoint",
        default="resources/data/test-results/character-mode-stage3-checkpoint.json",
    )
    verify.add_argument("--base-url")
    verify.add_argument("--timeout-seconds", type=float, default=120)
    verify.add_argument("--token-budget", type=int, default=4_000)
    verify.add_argument(
        "--report",
        default="resources/data/test-results/character-mode-stage3-final-report.json",
    )
    return parser


def _checkpoint(path: str) -> Stage3Checkpoint:
    return Stage3Checkpoint.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _with_base_url(checkpoint: Stage3Checkpoint, base_url: str | None) -> Stage3Checkpoint:
    resolved = base_url or checkpoint.base_url
    if resolved == checkpoint.base_url:
        return checkpoint
    return checkpoint.model_copy(update={"base_url": resolved})


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        config = Stage3PrepareConfig(
            base_url=args.base_url,
            provider_id=args.provider_id,
            model_id=args.model_id,
            maya_character_id=args.maya_character_id,
            alex_character_id=args.alex_character_id,
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
            settle_seconds=args.settle_seconds,
            token_budget=args.token_budget,
        )
        report = prepare_stage3(
            HttpStage3Gateway(config.base_url, config.timeout_seconds),
            config,
            checkpoint_path=args.checkpoint,
        )
    else:
        checkpoint = _with_base_url(_checkpoint(args.checkpoint), args.base_url)
        report = verify_stage3_restart(
            HttpStage3Gateway(checkpoint.base_url, args.timeout_seconds),
            checkpoint,
            token_budget=args.token_budget,
        )
    write_report(report, args.report)
    print(report.model_dump_json(indent=2))
    return 2 if report.decision == "blocked" else 0


__all__ = [
    "HttpStage3Gateway",
    "Stage3Check",
    "Stage3Checkpoint",
    "Stage3Gateway",
    "Stage3Metrics",
    "Stage3PrepareConfig",
    "Stage3Report",
    "main",
    "prepare_stage3",
    "verify_stage3_restart",
    "write_report",
]
