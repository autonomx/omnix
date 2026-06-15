from __future__ import annotations

import json
import sys
from pathlib import Path

from app.gateway.main import create_gateway_app


def test_generated_gateway_openapi_schema_is_current() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    generated_path = repo_root / "apps" / "web" / "src" / "api" / "generated" / "openapi.json"

    generated_schema = json.loads(generated_path.read_text(encoding="utf-8"))
    current_schema = create_gateway_app().openapi()

    if generated_schema != current_schema:
        print(
            "Generated gateway OpenAPI schema is stale. "
            "Run `npm --workspace @omnix/web run api:schema` and commit the result.",
            file=sys.stderr,
        )

    assert generated_schema == current_schema
