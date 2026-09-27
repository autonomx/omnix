from __future__ import annotations

import argparse
from pathlib import Path

from app.config.registry import render_configuration_markdown

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "CONFIGURATION.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
