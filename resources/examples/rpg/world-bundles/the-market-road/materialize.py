"""Write The Market Road's importable world bundle from its readable source (``world.source.json``).

Omnix builds the starter world from this source itself (``genesis/worlds/builtin_worlds.py``); this script writes
the same bundle to a file, to import by hand through Worlds & Campaigns or to share.

    python resources/examples/rpg/world-bundles/the-market-road/materialize.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

BUNDLE_FILENAME = "the-market-road.omnix-world.zip"


def build_bundle(source_dir: Path) -> bytes:
    from app.apps.rpg.genesis.worlds.world_source import build_bundle as build

    return build(json.loads((source_dir / "world.source.json").read_text(encoding="utf-8")))


def materialize_bundle(source_dir: Path, output: Path | None = None) -> Path:
    destination = output or source_dir.parent / BUNDLE_FILENAME
    destination.write_bytes(build_bundle(source_dir))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize The Market Road's Omnix world bundle")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    print(materialize_bundle(Path(__file__).resolve().parent, args.output))


if __name__ == "__main__":
    main()
