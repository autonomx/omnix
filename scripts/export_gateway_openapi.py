"""Export the thin Omnix gateway OpenAPI schema to disk."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/export_gateway_openapi.py <output-json>", file=sys.stderr)
        return 2

    root = _repo_root()
    src_dir = root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from app.gateway.main import create_gateway_app

    output_path = (root / argv[1]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_gateway_app().openapi()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
