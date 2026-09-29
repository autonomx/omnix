"""Generate or check the committed autoplay runtime source artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests.rpg.autoplay_fragment_codegen import (  # noqa: E402
    autoplay_campaign_fragments,
    combine_autoplay_campaign_fragments,
)


PARTS_DIR = ROOT / "src" / "tests" / "rpg" / "autoplay_llm_campaign_parts"
OUTPUT_PATH = ROOT / "src" / "tests" / "rpg" / "autoplay_llm_campaign.generated.pyfrag"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed artifact is stale")
    args = parser.parse_args()

    generated = combine_autoplay_campaign_fragments(autoplay_campaign_fragments(PARTS_DIR))
    if args.check:
        try:
            current = OUTPUT_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"generated autoplay runtime is missing: {exc}", file=sys.stderr)
            return 1
        if current != generated:
            print(f"generated autoplay runtime is stale: run {Path(__file__).name}", file=sys.stderr)
            return 1
        print(f"generated autoplay runtime is current ({len(generated.splitlines())} lines)")
        return 0

    OUTPUT_PATH.write_text(generated, encoding="utf-8", newline="\n")
    print(f"generated {OUTPUT_PATH.relative_to(ROOT)} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
