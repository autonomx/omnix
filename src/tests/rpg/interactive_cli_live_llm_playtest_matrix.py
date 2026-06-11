"""Phase 13.99 — opt-in live LLM scenario-pack matrix runner.

Runs one or more named live LLM playtest scenario packs, persists per-pack
quality summaries, and aggregates the summaries for nightly/manual review.  The
underlying playtest runner remains opt-in, so this module is safe to import in
normal deterministic CI.
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

from tests.rpg.interactive_cli_live_llm_playtest import (  # noqa: E402
    LIVE_LLM_PLAYTEST_ENV_FLAG,
    LIVE_LLM_PLAYTEST_SCENARIO_PACKS,
    list_live_llm_playtest_scenario_packs,
    run_live_llm_playtest,
)
from tests.rpg.interactive_cli_live_quality_eval import (  # noqa: E402
    aggregate_live_quality_eval_summary_files,
    write_live_quality_aggregate_summary,
)

LIVE_LLM_PLAYTEST_MATRIX_VERSION = "rpg_live_llm_playtest_matrix_v1"
LIVE_LLM_PLAYTEST_MATRIX_STATUS_MARKER = "RPG_LIVE_LLM_PLAYTEST_MATRIX"
DEFAULT_LIVE_LLM_PLAYTEST_MATRIX_DIRNAME = "live-llm-playtest-matrix"


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _slug(value: str) -> str:
    text = _safe_str(value).strip().lower()
    out = []
    for char in text:
        if char.isalnum():
            out.append(char)
        elif char in {"-", "_"}:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "scenario"


def resolve_live_llm_playtest_matrix_packs(packs: Sequence[str] | None = None) -> list[str]:
    """Resolve selected scenario packs or all built-in packs when omitted."""

    selected = [_safe_str(pack).strip() for pack in packs or [] if _safe_str(pack).strip()]
    if not selected:
        return sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS)
    available = set(LIVE_LLM_PLAYTEST_SCENARIO_PACKS)
    unknown = sorted(pack for pack in selected if pack not in available)
    if unknown:
        return []
    # Preserve caller order while removing duplicates deterministically.
    result: list[str] = []
    seen: set[str] = set()
    for pack in selected:
        if pack not in seen:
            result.append(pack)
            seen.add(pack)
    return result


def _unknown_packs_error(packs: Sequence[str]) -> dict[str, Any] | None:
    selected = [_safe_str(pack).strip() for pack in packs if _safe_str(pack).strip()]
    available = set(LIVE_LLM_PLAYTEST_SCENARIO_PACKS)
    unknown = sorted(pack for pack in selected if pack not in available)
    if not unknown:
        return None
    return {
        "format_version": LIVE_LLM_PLAYTEST_MATRIX_VERSION,
        "ok": False,
        "skipped": False,
        "error": "unknown_live_llm_playtest_matrix_pack",
        "unknown_packs": unknown,
        "available_packs": sorted(available),
    }


def render_live_llm_playtest_matrix_status_marker(result: Mapping[str, Any]) -> str:
    """Render one scrapeable status line for matrix logs."""

    aggregate = _safe_dict(result.get("aggregate"))
    ok = "true" if bool(result.get("ok")) else "false"
    skipped = "true" if bool(result.get("skipped")) else "false"
    pack_count = int(result.get("pack_count") or len(result.get("packs") if isinstance(result.get("packs"), list) else []))
    passed = int(aggregate.get("passed") or 0)
    failed = int(aggregate.get("failed") or 0)
    avg_score = float(aggregate.get("avg_score") or 0.0)
    fun = float(_safe_dict(aggregate.get("scores")).get("fun") or 0.0)
    failure_types = _safe_list(aggregate.get("failure_types"))
    error = _safe_str(
        result.get("error")
        or aggregate.get("error")
        or (failure_types[0] if failure_types else "none")
    )
    return (
        f"[{LIVE_LLM_PLAYTEST_MATRIX_STATUS_MARKER}] ok={ok} skipped={skipped} "
        f"pack_count={pack_count} passed={passed} failed={failed} "
        f"avg_score={avg_score:.3f} fun={fun:.3f} error={error}"
    )


def run_live_llm_playtest_matrix(
    *,
    scenario_packs: Sequence[str] | None = None,
    allow_live: bool = False,
    output_dir: str | Path | None = None,
    turns: int | None = None,
    run_id_prefix: str = "live-matrix",
    session_id_prefix: str = "interactive_cli_live_matrix",
    reset_session: bool = True,
    console_llm: bool = False,
    seed_live_survival: bool = True,
    artifact_detail: str = "debug",
    aggregate_path: str | Path | None = None,
    playtest_runner: Any | None = None,
) -> dict[str, Any]:
    """Run selected live LLM scenario packs and aggregate their quality summaries."""

    requested_packs = list(scenario_packs or [])
    error = _unknown_packs_error(requested_packs)
    if error:
        return error
    packs = resolve_live_llm_playtest_matrix_packs(requested_packs)
    resolved_output_dir = Path(output_dir) if output_dir else Path("artifacts") / DEFAULT_LIVE_LLM_PLAYTEST_MATRIX_DIRNAME
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    runner = playtest_runner or run_live_llm_playtest

    runs: list[dict[str, Any]] = []
    summary_paths: list[Path] = []
    for index, pack in enumerate(packs, start=1):
        slug = _slug(pack)
        pack_output_dir = resolved_output_dir / f"{index:02d}-{slug}"
        quality_summary_path = pack_output_dir / "live-quality-summary.json"
        result = runner(
            turns=turns,
            session_id=f"{session_id_prefix}_{slug}",
            run_id=f"{run_id_prefix}-{slug}",
            output_dir=pack_output_dir,
            scenario_pack=pack,
            allow_live=allow_live,
            reset_session=reset_session,
            console_llm=console_llm,
            seed_live_survival=seed_live_survival,
            artifact_detail=artifact_detail,
            summary_path=quality_summary_path,
        )
        run_entry = {
            "scenario_pack": pack,
            "ok": bool(_safe_dict(result).get("ok")),
            "skipped": bool(_safe_dict(result).get("skipped")),
            "output_dir": str(pack_output_dir),
            "quality_summary_path": str(quality_summary_path),
            "error": _safe_str(_safe_dict(result).get("error") or "none"),
        }
        if quality_summary_path.exists():
            summary_paths.append(quality_summary_path)
        runs.append(run_entry)

    aggregate = aggregate_live_quality_eval_summary_files(summary_paths)
    resolved_aggregate_path = Path(aggregate_path) if aggregate_path else resolved_output_dir / "live-quality-aggregate.json"
    write_live_quality_aggregate_summary(result=aggregate, aggregate_path=resolved_aggregate_path)
    skipped = bool(runs) and all(run.get("skipped") for run in runs)
    result = {
        "format_version": LIVE_LLM_PLAYTEST_MATRIX_VERSION,
        "ok": bool(aggregate.get("ok")) and len(summary_paths) == len(packs),
        "skipped": skipped,
        "pack_count": len(packs),
        "packs": packs,
        "output_dir": str(resolved_output_dir),
        "aggregate_path": str(resolved_aggregate_path),
        "summary_paths": [str(path) for path in summary_paths],
        "runs": runs,
        "aggregate": aggregate,
    }
    if len(summary_paths) != len(packs):
        result["ok"] = False
        result["error"] = next((run.get("error") for run in runs if run.get("skipped") and run.get("error") != "none"), "live_llm_playtest_matrix_missing_summaries")
        result["missing_summary_count"] = len(packs) - len(summary_paths)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run opt-in live LLM scenario packs and aggregate transcript quality summaries.")
    parser.add_argument("--scenario-pack", action="append", default=[], choices=sorted(LIVE_LLM_PLAYTEST_SCENARIO_PACKS), help="Scenario pack to run; may be repeated. Defaults to all packs.")
    parser.add_argument("--list-scenario-packs", action="store_true", help="List built-in scenario packs and exit.")
    parser.add_argument("--allow-live", action="store_true", help=f"Allow live provider execution without setting {LIVE_LLM_PLAYTEST_ENV_FLAG}=1.")
    parser.add_argument("--turns", type=int, default=0, help="Optional turn override for each pack.")
    parser.add_argument("--output-dir", default="", help="Output directory for all pack runs and aggregate summary.")
    parser.add_argument("--aggregate-path", default="", help="Optional path to persist aggregate quality JSON.")
    parser.add_argument("--run-id-prefix", default="live-matrix")
    parser.add_argument("--session-id-prefix", default="interactive_cli_live_matrix")
    parser.add_argument("--no-reset-session-state", action="store_true")
    parser.add_argument("--console-llm", action="store_true")
    parser.add_argument("--no-live-survival-seed", action="store_true")
    parser.add_argument("--artifact-detail", choices=["summary", "debug", "full"], default="debug")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.list_scenario_packs:
        print(json.dumps({"scenario_packs": list_live_llm_playtest_scenario_packs()}, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    result = run_live_llm_playtest_matrix(
        scenario_packs=args.scenario_pack,
        allow_live=bool(args.allow_live),
        output_dir=args.output_dir or None,
        turns=int(args.turns or 0) or None,
        run_id_prefix=args.run_id_prefix,
        session_id_prefix=args.session_id_prefix,
        reset_session=not bool(args.no_reset_session_state),
        console_llm=bool(args.console_llm),
        seed_live_survival=not bool(args.no_live_survival_seed),
        artifact_detail=args.artifact_detail,
        aggregate_path=args.aggregate_path or None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_live_llm_playtest_matrix_status_marker(result), file=sys.stderr)
    if result.get("skipped"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
