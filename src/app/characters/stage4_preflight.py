"""CLI for the Character Mode Stage 4 shared-memory pilot."""
from __future__ import annotations

import argparse
from pathlib import Path

from .stage4_contracts import Stage4Checkpoint, Stage4PrepareConfig, write_report
from .stage4_http import HttpStage4Gateway
from .stage4_runner import prepare_stage4, verify_stage4_restart


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Character Mode Stage 4 shared-memory pilot.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--base-url", default=Stage4PrepareConfig().base_url)
    prepare.add_argument("--provider-id", default="lmstudio")
    prepare.add_argument("--model-id", required=True)
    prepare.add_argument("--character-id", default="stage4-maya")
    prepare.add_argument("--run-id", default="stage4-shared-readonly-v1")
    prepare.add_argument("--timeout-seconds", type=float, default=120)
    prepare.add_argument("--checkpoint", default="resources/data/test-results/character-mode-stage4-checkpoint.json")
    prepare.add_argument("--report", default="resources/data/test-results/character-mode-stage4-prepare-report.json")
    verify = commands.add_parser("verify-restart")
    verify.add_argument("--checkpoint", default="resources/data/test-results/character-mode-stage4-checkpoint.json")
    verify.add_argument("--base-url")
    verify.add_argument("--timeout-seconds", type=float, default=120)
    verify.add_argument("--report", default="resources/data/test-results/character-mode-stage4-final-report.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        config = Stage4PrepareConfig(
            base_url=args.base_url, provider_id=args.provider_id, model_id=args.model_id,
            character_id=args.character_id, run_id=args.run_id, timeout_seconds=args.timeout_seconds,
        )
        report = prepare_stage4(HttpStage4Gateway(config.base_url, config.timeout_seconds), config, checkpoint_path=args.checkpoint)
    else:
        checkpoint = Stage4Checkpoint.model_validate_json(Path(args.checkpoint).read_text(encoding="utf-8"))
        if args.base_url:
            checkpoint = checkpoint.model_copy(update={"base_url": args.base_url})
        report = verify_stage4_restart(HttpStage4Gateway(checkpoint.base_url, args.timeout_seconds), checkpoint)
    write_report(report, args.report)
    print(report.model_dump_json(indent=2))
    return 2 if report.decision == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
