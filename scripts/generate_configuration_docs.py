from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUTPUT = ROOT / "docs" / "CONFIGURATION.md"


def main() -> int:
    from generate_configuration_registry import discover_variables, OUTPUT as REGISTRY_OUTPUT
    from app.config.registry import render_configuration_markdown

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected_registry = json.dumps(
        discover_variables(), indent=2, sort_keys=True
    ) + "\n"
    current_registry = REGISTRY_OUTPUT.read_text(encoding="utf-8") if REGISTRY_OUTPUT.exists() else ""
    if args.check and current_registry != expected_registry:
        raise SystemExit(
            "configuration registry is stale; run scripts/generate_configuration_registry.py"
        )
    rendered = render_configuration_markdown()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            raise SystemExit("docs/CONFIGURATION.md is stale; run scripts/generate_configuration_docs.py")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
