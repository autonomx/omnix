"""Projection of authoritative Pydantic schemas into provider-safe variants."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .contracts import StructuredMode

_DROP_KEYS = {
    "default",
    "description",
    "examples",
    "title",
}


def _resolve_ref(root: Mapping[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        return None
    value: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return copy.deepcopy(value)


def _project_node(node: Any, *, root: Mapping[str, Any], inline_refs: bool) -> Any:
    if isinstance(node, list):
        return [_project_node(value, root=root, inline_refs=inline_refs) for value in node]
    if not isinstance(node, Mapping):
        return node
    if inline_refs and isinstance(node.get("$ref"), str):
        resolved = _resolve_ref(root, str(node["$ref"]))
        if resolved is not None:
            merged = dict(resolved)
            merged.update({key: value for key, value in node.items() if key != "$ref"})
            return _project_node(merged, root=root, inline_refs=inline_refs)
    projected: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROP_KEYS or key == "$defs":
            continue
        projected[key] = _project_node(value, root=root, inline_refs=inline_refs)
    return projected


def project_provider_schema(
    schema: Mapping[str, Any],
    *,
    mode: StructuredMode,
    provider_name: str = "",
    schema_profile: str = "default",
) -> dict[str, Any]:
    """Return a conservative schema suitable for a provider endpoint.

    Python/Pydantic validation remains authoritative. The projection removes
    documentation-only annotations and inlines references for local/schema
    endpoints that commonly reject `$defs` or `$ref`.
    """

    normalized_provider = str(provider_name or "").strip().casefold()
    inline_refs = mode is StructuredMode.JSON_SCHEMA and (
        normalized_provider == "lmstudio" or schema_profile in {"local", "canon_strict"}
    )
    projected = _project_node(dict(schema), root=schema, inline_refs=inline_refs)
    if not isinstance(projected, dict):
        raise TypeError("projected structured schema must be an object")
    return projected
