"""Export the thin Omnix gateway OpenAPI schema to disk."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stabilize_equivalent_io_schemas(schema: dict[str, object]) -> None:
    """Preserve legacy input/output component identities when they are equivalent.

    FastAPI/Pydantic releases can deduplicate a model's validation and
    serialization schemas when their structures are identical. Omnix commits the
    generated gateway contract, so that implementation-level optimization would
    otherwise create unrelated contract churn even though the public schema did
    not change.

    AssistantToolsConfigPayload historically has explicit ``-Input`` and
    ``-Output`` components, and the two structures are intentionally identical.
    If the generator collapses them to one equivalent component, expand that
    component back to the stable checked-in identities. This changes names only;
    it never rewrites fields, requirements, types, or endpoint paths.
    """

    components = schema.get("components")
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        return

    canonical_name = "AssistantToolsConfigPayload"
    input_name = f"{canonical_name}-Input"
    output_name = f"{canonical_name}-Output"
    value = schemas.get(canonical_name)
    if (
        not isinstance(value, dict)
        or input_name in schemas
        or output_name in schemas
    ):
        return

    # Keep this normalization deliberately narrow. If future input/output
    # contracts genuinely diverge, FastAPI will emit distinct components and
    # this branch will not run.
    schemas[input_name] = copy.deepcopy(value)
    schemas[output_name] = copy.deepcopy(value)
    del schemas[canonical_name]


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
    _stabilize_equivalent_io_schemas(schema)
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
