"""Production modules no entry point reaches, grouped by package (WP-8.6).

    python scripts/reachability_report.py [--prefix app.apps.rpg.] [--json]

Uses the same static import graph as the ``unreachable_rpg_modules`` metric
(see ``architecture_metrics.unreachable_python`` for the roots). Before deleting
a module the report lists, also search for its path and dotted name in
resources and docs (roadmap Appendix G). Exits 1 when anything is unreachable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from architecture_analysis import SourceAnalysis, load_layers, module_name, top_package, tracked_sources  # noqa: E402
from architecture_metrics import unreachable_python  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def report(root: Path, prefix: str) -> dict[str, list[str]]:
    """Unreachable module paths keyed by their top-level package."""
    analysis = SourceAnalysis(tracked_sources(root), load_layers(root / "resources/architecture/layers.toml"))
    grouped: dict[str, list[str]] = {}
    for path in unreachable_python(analysis, prefix):
        grouped.setdefault(top_package(module_name(path)), []).append(path)
    return grouped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--prefix", default="app.", help="dotted module prefix to report (default: every app module)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    grouped = report(args.root.resolve(), args.prefix)
    if args.json:
        print(json.dumps(grouped, indent=2, sort_keys=True))
    else:
        for package in sorted(grouped):
            print(f"{package}: {len(grouped[package])}")
            for path in grouped[package]:
                print(f"  {path}")
        print(f"unreachable: {sum(len(paths) for paths in grouped.values())}")
    return 1 if grouped else 0


if __name__ == "__main__":
    raise SystemExit(main())
