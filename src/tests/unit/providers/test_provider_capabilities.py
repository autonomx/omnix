"""Callers select provider behaviour by catalog capability, not by name (WP-7.2)."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.providers import catalog
from app.providers.catalog import (
    CLOSED_OBJECT_SCHEMA,
    CONVERSATION_SESSIONS,
    LOCAL_DEVICE,
    NATIVE_JSON_SCHEMA,
    ProviderSpec,
    provider_supports,
    providers_with,
)
from app.providers.structured.contracts import StructuredCapabilities, StructuredMode

APP = Path(__file__).resolve().parents[3] / "app"
# The provider package maps its own settings to configurations by id, and RPG
# leaves with WP-8.6.
EXEMPT = (APP / "providers", APP / "rpg")


def test_capabilities_are_looked_up_by_id_or_instance() -> None:
    codex = SimpleNamespace(provider_name="chatgpt_codex")
    configured = SimpleNamespace(config=SimpleNamespace(provider_type="lmstudio"))

    assert provider_supports("chatgpt_codex", CONVERSATION_SESSIONS)
    assert provider_supports("llm:ChatGPT_Codex", CONVERSATION_SESSIONS)
    assert provider_supports(codex, CLOSED_OBJECT_SCHEMA)
    assert provider_supports(configured, LOCAL_DEVICE)
    assert not provider_supports("openrouter", LOCAL_DEVICE)
    assert not provider_supports("not-a-provider", LOCAL_DEVICE)
    assert not provider_supports(None, LOCAL_DEVICE)
    assert set(providers_with(LOCAL_DEVICE)) == {"lmstudio", "llamacpp"}


def test_an_unknown_capability_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown provider capability"):
        provider_supports("lmstudio", "telepathy")
    bogus = ProviderSpec("x", "llm", "app.providers.x", "X", frozenset({"chat", "telepathy"}))
    with pytest.raises(ValueError, match="unknown capabilities"):
        catalog._check_unique((bogus,))


def test_a_new_provider_gains_behaviour_by_declaring_it(monkeypatch) -> None:
    spec = ProviderSpec(
        "future_local", "llm", "app.providers.future", "Future",
        frozenset({"chat", LOCAL_DEVICE, NATIVE_JSON_SCHEMA}),
    )
    monkeypatch.setattr(catalog, "CATALOG", (*catalog.CATALOG, spec))

    assert provider_supports("future_local", LOCAL_DEVICE)
    structured = StructuredCapabilities.default_for_provider("future_local")
    assert structured.preferred_modes[0] is StructuredMode.JSON_SCHEMA
    assert structured.supports_strict_schema


def _provider_name_comparisons(path: Path) -> list[int]:
    ids = {spec.id for spec in catalog.specs("llm")}
    found: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for index, operator in enumerate(node.ops):
            if isinstance(operator, (ast.In, ast.NotIn)):
                # ``provider in {...}`` names providers; ``"lmstudio" in data``
                # looks up a settings key.
                compared = [operands[index + 1]]
            elif isinstance(operator, (ast.Eq, ast.NotEq)):
                compared = operands[index:index + 2]
            else:
                continue
            values = [
                value
                for operand in compared
                for value in (operand.elts if isinstance(operand, (ast.Tuple, ast.Set, ast.List)) else [operand])
            ]
            if any(isinstance(value, ast.Constant) and value.value in ids for value in values):
                found.append(node.lineno)
                break
    return found


def test_no_caller_compares_provider_names() -> None:
    offenders = {
        str(path.relative_to(APP)): lines
        for path in sorted(APP.rglob("*.py"))
        if not any(path.is_relative_to(root) for root in EXEMPT)
        and (lines := _provider_name_comparisons(path))
    }
    assert offenders == {}, "ask app.providers.catalog for a capability instead"
