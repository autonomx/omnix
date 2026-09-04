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


def _project_node(
    node: Any,
    *,
    root: Mapping[str, Any],
    inline_refs: bool,
    extra_drop_keys: frozenset[str],
) -> Any:
    if isinstance(node, list):
        return [
            _project_node(
                value,
                root=root,
                inline_refs=inline_refs,
                extra_drop_keys=extra_drop_keys,
            )
            for value in node
        ]
    if not isinstance(node, Mapping):
        return node
    if inline_refs and isinstance(node.get("$ref"), str):
        resolved = _resolve_ref(root, str(node["$ref"]))
        if resolved is not None:
            merged = dict(resolved)
            merged.update({key: value for key, value in node.items() if key != "$ref"})
            return _project_node(
                merged,
                root=root,
                inline_refs=inline_refs,
                extra_drop_keys=extra_drop_keys,
            )
    projected: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROP_KEYS or key in extra_drop_keys or key == "$defs":
            continue
        projected[key] = _project_node(
            value,
            root=root,
            inline_refs=inline_refs,
            extra_drop_keys=extra_drop_keys,
        )
    return projected


def _require_all_object_properties(node: Any) -> Any:
    """Make every object property explicit in provider-facing strict schemas.

    OpenAI/Codex strict structured-output validators require an object's
    ``required`` array to contain every key declared under ``properties``.
    Pydantic intentionally omits defaulted/optional fields from ``required``;
    changing the authoritative Python models would remove useful defaults, so
    normalize only the projected provider schema instead. Nullable fields stay
    nullable through their existing ``anyOf[..., null]`` representation.
    """

    if isinstance(node, list):
        return [_require_all_object_properties(value) for value in node]
    if not isinstance(node, Mapping):
        return node

    normalized = {
        key: _require_all_object_properties(value)
        for key, value in node.items()
    }
    properties = normalized.get("properties")
    if isinstance(properties, Mapping):
        normalized["required"] = list(properties.keys())
    return normalized


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
    endpoints that commonly reject `$defs` or `$ref`. Canon publication keeps
    length validation in Python while omitting it from the simplified provider
    grammar for compatibility with older local structured-output endpoints.

    ChatGPT Codex uses OpenAI-compatible strict object-schema validation even
    though its app-server adapter currently transports the contract via the
    provider abstraction. Its provider-facing JSON schema therefore lists every
    object property as required, while nullable Pydantic fields remain nullable.
    """

    normalized_provider = str(provider_name or "").strip().casefold()
    inline_refs = mode is StructuredMode.JSON_SCHEMA and (
        normalized_provider == "lmstudio" or schema_profile in {"local", "canon_strict"}
    )
    extra_drop_keys = (
        frozenset({"minLength"})
        if schema_profile == "canon_strict"
        else frozenset()
    )
    projected = _project_node(
        dict(schema),
        root=schema,
        inline_refs=inline_refs,
        extra_drop_keys=extra_drop_keys,
    )
    if not isinstance(projected, dict):
        raise TypeError("projected structured schema must be an object")

    if mode is StructuredMode.JSON_SCHEMA and normalized_provider == "chatgpt_codex":
        projected = _require_all_object_properties(projected)
        if not isinstance(projected, dict):
            raise TypeError("strict projected structured schema must be an object")

    if schema_profile == "canon_strict":
        # Canon provenance is server-authored after validation. Leaving this
        # provider field open-ended lets a local guided decoder legally emit
        # the complete authorship ledger and exhaust its completion budget.
        # Keep the required transport field, but constrain it to a placeholder.
        properties = projected.get("properties")
        if isinstance(properties, dict) and "provenance" in properties:
            properties["provenance"] = {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
    return projected
