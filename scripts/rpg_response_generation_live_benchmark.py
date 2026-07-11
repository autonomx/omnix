from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.rpg.response_generation.baseline import (
    evaluate_baseline,
    load_baseline_scenarios,
    load_observations,
)


DEFAULT_FIXTURE = Path(
    "src/tests/rpg/response_generation/fixtures/response_generation_baseline_v1.json"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate opt-in live-model RPG response observations against the "
            "human-labeled response-generation baseline."
        )
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--observations",
        type=Path,
        required=True,
        help="JSON file containing an observations list produced by a live runner.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if os.environ.get("OMNIX_RPG_RESPONSE_LIVE_BENCHMARK") != "1":
        raise SystemExit(
            "Set OMNIX_RPG_RESPONSE_LIVE_BENCHMARK=1 to run the informational "
            "live-model benchmark. It is intentionally excluded from deterministic CI."
        )

    scenarios = load_baseline_scenarios(args.fixture)
    observations = load_observations(args.observations)
    metrics = evaluate_baseline(scenarios, observations)
    report: dict[str, Any] = {
        "format_version": "rpg_response_live_benchmark_v1",
        "informational_only": True,
        "fixture": str(args.fixture),
        "observations": str(args.observations),
        "metrics": metrics.as_dict(),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
