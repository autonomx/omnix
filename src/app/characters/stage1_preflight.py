"""CLI and public exports for the Character Mode Stage 1 rehearsal."""
from __future__ import annotations

import argparse
from pathlib import Path

from .stage1_contracts import (
    Stage1Check,
    Stage1Checkpoint,
    Stage1Metrics,
    Stage1PrepareConfig,
    Stage1Report,
    write_report,
)
from .stage1_http import HttpStage1Gateway, Stage1Gateway
from .stage1_runner import prepare_stage1, verify_stage1_restart


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Omnix Character Mode Stage 1 identity-without-memory rehearsal."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Run Stage 1 and create a restart checkpoint.",
    )
    prepare.add_argument("--base-url", default="http://127.0.0.1:5050")
    prepare.add_argument("--character-id", default="stage1-maya")
    prepare.add_argument("--display-name", default="Maya Stage 1")
    prepare.add_argument(
        "--personality-prompt",
        default=Stage1PrepareConfig().personality_prompt,
    )
    prepare.add_argument("--greeting", default="Hey, good to hear from you.")
    prepare.add_argument("--voice-asset-id")
    prepare.add_argument("--provider-id")
    prepare.add_argument("--model-id")
    prepare.add_argument("--probe-text", default=Stage1PrepareConfig().probe_text)
    prepare.add_argument("--timeout-seconds", type=float, default=120)
    prepare.add_argument("--settle-seconds", type=float, default=1.5)
    prepare.add_argument("--skip-generation", action="store_true")
    prepare.add_argument("--skip-tts", action="store_true")
    prepare.add_argument("--update-existing-character", action="store_true")
    prepare.add_argument("--apply-voice-governance", action="store_true")
    prepare.add_argument("--confirm-voice-consent", action="store_true")
    prepare.add_argument("--voice-subject-owner", default="")
    prepare.add_argument("--voice-source-type", default="")
    prepare.add_argument("--voice-source-reference", default="")
    prepare.add_argument("--voice-creator-id", default="")
    prepare.add_argument(
        "--checkpoint",
        default="resources/data/test-results/character-mode-stage1-checkpoint.json",
    )
    prepare.add_argument(
        "--report",
        default="resources/data/test-results/character-mode-stage1-prepare-report.json",
    )

    verify = subparsers.add_parser(
        "verify-restart",
        help="After restarting Omnix, verify the persisted Stage 1 checkpoint.",
    )
    verify.add_argument(
        "--checkpoint",
        default="resources/data/test-results/character-mode-stage1-checkpoint.json",
    )
    verify.add_argument("--base-url")
    verify.add_argument("--timeout-seconds", type=float, default=120)
    verify.add_argument(
        "--report",
        default="resources/data/test-results/character-mode-stage1-final-report.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        config = Stage1PrepareConfig(
            base_url=args.base_url,
            character_id=args.character_id,
            display_name=args.display_name,
            personality_prompt=args.personality_prompt,
            greeting=args.greeting,
            voice_asset_id=args.voice_asset_id,
            provider_id=args.provider_id,
            model_id=args.model_id,
            probe_text=args.probe_text,
            timeout_seconds=args.timeout_seconds,
            settle_seconds=args.settle_seconds,
            skip_generation=args.skip_generation,
            skip_tts=args.skip_tts,
            update_existing_character=args.update_existing_character,
            apply_voice_governance=args.apply_voice_governance,
            confirm_voice_consent=args.confirm_voice_consent,
            voice_subject_owner=args.voice_subject_owner,
            voice_source_type=args.voice_source_type,
            voice_source_reference=args.voice_source_reference,
            voice_creator_id=args.voice_creator_id,
        )
        report = prepare_stage1(
            HttpStage1Gateway(config.base_url, config.timeout_seconds),
            config,
            checkpoint_path=args.checkpoint,
        )
        write_report(report, args.report)
    else:
        checkpoint_path = Path(args.checkpoint)
        checkpoint = Stage1Checkpoint.model_validate_json(
            checkpoint_path.read_text(encoding="utf-8")
        )
        base_url = args.base_url or checkpoint.base_url
        if base_url != checkpoint.base_url:
            checkpoint = checkpoint.model_copy(update={"base_url": base_url})
        report = verify_stage1_restart(
            HttpStage1Gateway(base_url, args.timeout_seconds),
            checkpoint,
        )
        write_report(report, args.report)
    print(report.model_dump_json(indent=2))
    return 2 if report.decision == "blocked" else 0


__all__ = [
    "HttpStage1Gateway",
    "Stage1Check",
    "Stage1Checkpoint",
    "Stage1Gateway",
    "Stage1Metrics",
    "Stage1PrepareConfig",
    "Stage1Report",
    "main",
    "prepare_stage1",
    "verify_stage1_restart",
    "write_report",
]
