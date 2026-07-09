"""CLI and public exports for the Character Mode Stage 2 read-only pilot."""
from __future__ import annotations

import argparse
from pathlib import Path

from .stage2_contracts import (
    Stage2Check,
    Stage2Checkpoint,
    Stage2Metrics,
    Stage2PrepareConfig,
    Stage2Report,
    write_report,
)
from .stage2_http import HttpStage2Gateway, Stage2Gateway
from .stage2_runner import prepare_stage2, verify_stage2_restart


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Omnix Character Mode Stage 2 read-only memory pilot."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Seed controlled owner fixtures and run the read-only pilot.",
    )
    prepare.add_argument("--base-url", default=Stage2PrepareConfig().base_url)
    prepare.add_argument("--provider-id", default="lmstudio")
    prepare.add_argument("--model-id", required=True)
    prepare.add_argument("--maya-character-id", default="stage2-maya")
    prepare.add_argument("--alex-character-id", default="stage2-alex")
    prepare.add_argument("--run-id", default="stage2-readonly-v1")
    prepare.add_argument("--timeout-seconds", type=float, default=120)
    prepare.add_argument("--settle-seconds", type=float, default=4)
    prepare.add_argument("--token-budget", type=int, default=4_000)
    prepare.add_argument(
        "--checkpoint",
        default="resources/data/test-results/character-mode-stage2-checkpoint.json",
    )
    prepare.add_argument(
        "--report",
        default="resources/data/test-results/character-mode-stage2-prepare-report.json",
    )

    verify = subparsers.add_parser(
        "verify-restart",
        help="Verify the Stage 2 read-only checkpoint after restarting Omnix.",
    )
    verify.add_argument(
        "--checkpoint",
        default="resources/data/test-results/character-mode-stage2-checkpoint.json",
    )
    verify.add_argument("--base-url")
    verify.add_argument("--timeout-seconds", type=float, default=120)
    verify.add_argument("--settle-seconds", type=float, default=4)
    verify.add_argument("--token-budget", type=int, default=4_000)
    verify.add_argument(
        "--report",
        default="resources/data/test-results/character-mode-stage2-final-report.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        config = Stage2PrepareConfig(
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
        report = prepare_stage2(
            HttpStage2Gateway(config.base_url, config.timeout_seconds),
            config,
            checkpoint_path=args.checkpoint,
        )
        write_report(report, args.report)
    else:
        checkpoint_path = Path(args.checkpoint)
        checkpoint = Stage2Checkpoint.model_validate_json(
            checkpoint_path.read_text(encoding="utf-8")
        )
        base_url = args.base_url or checkpoint.base_url
        if base_url != checkpoint.base_url:
            checkpoint = checkpoint.model_copy(update={"base_url": base_url})
        report = verify_stage2_restart(
            HttpStage2Gateway(base_url, args.timeout_seconds),
            checkpoint,
            settle_seconds=args.settle_seconds,
            token_budget=args.token_budget,
        )
        write_report(report, args.report)
    print(report.model_dump_json(indent=2))
    return 2 if report.decision == "blocked" else 0


__all__ = [
    "HttpStage2Gateway",
    "Stage2Check",
    "Stage2Checkpoint",
    "Stage2Gateway",
    "Stage2Metrics",
    "Stage2PrepareConfig",
    "Stage2Report",
    "main",
    "prepare_stage2",
    "verify_stage2_restart",
    "write_report",
]
