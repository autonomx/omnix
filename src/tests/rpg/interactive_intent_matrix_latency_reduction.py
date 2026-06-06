"""Phase 13.4 interactive intent matrix latency-reduction runner.

This wrapper keeps the normal matrix unchanged while providing an opt-in runner
that patches the first-call advisory functions for accepted slow provider-backed
matrix paths. Canonical runtime still resolves state.
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Sequence

THIS_FILE = Path(__file__).resolve()
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.rpg.session.provider_backed_intent_fast_path import (  # noqa: E402
    FAST_PATH_SOURCE,
    build_provider_backed_fast_path_advisory,
)
from tests.rpg import interactive_intent_matrix as matrix  # noqa: E402


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


@contextmanager
def provider_backed_matrix_fast_path_patch() -> Iterator[None]:
    """Patch matrix first-call advisory lookup for accepted slow paths only."""
    from app.rpg.session import interactive_first_call_runtime as runtime

    original_action: Callable[..., Dict[str, Any]] = runtime.get_action_advisory
    original_semantic: Callable[..., Dict[str, Any]] = runtime.get_semantic_action_advisory

    def patched_action_advisory(**kwargs: Any) -> Dict[str, Any]:
        fast = build_provider_backed_fast_path_advisory(
            player_input=str(kwargs.get("player_input") or ""),
            performance_override=_safe_dict(kwargs.get("performance_override")),
        )
        if fast:
            return fast
        return original_action(**kwargs)

    def patched_semantic_action_advisory(**kwargs: Any) -> Dict[str, Any]:
        fast = build_provider_backed_fast_path_advisory(
            player_input=str(kwargs.get("player_input") or ""),
            performance_override=_safe_dict(kwargs.get("performance_override")),
        )
        if fast:
            return {}
        return original_semantic(**kwargs)

    runtime.get_action_advisory = patched_action_advisory  # type: ignore[assignment]
    runtime.get_semantic_action_advisory = patched_semantic_action_advisory  # type: ignore[assignment]
    try:
        yield
    finally:
        runtime.get_action_advisory = original_action  # type: ignore[assignment]
        runtime.get_semantic_action_advisory = original_semantic  # type: ignore[assignment]


def run_latency_reduced_intent_matrix(
    *,
    scenarios: Sequence[matrix.IntentMatrixScenario] | None = None,
    output_root: Path | None = None,
    live_provider: bool = True,
    seed_live_survival: bool = True,
) -> Dict[str, Any]:
    with provider_backed_matrix_fast_path_patch():
        return matrix.run_intent_matrix(
            scenarios=scenarios,
            output_root=output_root,
            live_provider=live_provider,
            seed_live_survival=seed_live_survival,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 13.4 latency-reduced interactive intent matrix.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider where a fast path is not selected.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This matrix is intended for live provider regression runs. Re-run with --live-provider.")
        return 2
    scenarios = matrix._select_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else matrix.DEFAULT_OUTPUT_ROOT
    result = run_latency_reduced_intent_matrix(
        scenarios=scenarios,
        output_root=output_root,
        live_provider=True,
        seed_live_survival=not bool(args.no_live_survival_seed),
    )
    summary = dict(result["summary"])
    summary["phase13_4_latency_reduction"] = {
        "enabled": True,
        "source": FAST_PATH_SOURCE,
        "bounded_target": "provider_backed_intent_paths",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if not summary.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
