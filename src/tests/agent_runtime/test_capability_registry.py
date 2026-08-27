from __future__ import annotations

from app.agent_runtime.capabilities import default_capability_registry
from app.assistant_tools.registry import default_assistant_tools
from app.assist_core.hermes_catalog import hermes_catalog_specs


def test_capability_registry_is_the_canonical_projection_source() -> None:
    registry = default_capability_registry()
    assert registry.canonical_id("kasa_turn_on") == "kasa.turn_on"
    assert registry.get("github.merge_pr").execution_zone == "broker"
    assert registry.get("github.merge_pr").risk == "high"

    assistant_ids = {
        action.id
        for tool in default_assistant_tools()
        for action in tool.actions
    }
    assert "kasa.turn_on" in assistant_ids
    assert "github.merge_pr" in assistant_ids

    hermes_ids = {tool.name for tool in hermes_catalog_specs()}
    assert "kasa.turn_on" in hermes_ids
    assert "kasa_turn_on" not in hermes_ids
