"""The tool catalog and every authority-relevant field (PA-1.4).

A permanent golden: any change to which tools exist, their risk, approval,
scope, schemas or visibility is a reviewed behavior change. Operator MCP tools
are excluded because they come from the local MCP policy file.
"""
from __future__ import annotations

from app.capabilities.registry import TOOL_DECLARATIONS, _definition_hash, default_capability_registry
from app.research.assistant_tool import ResearchTool
from app.runtime.ports import PortBinding, PortBindings, install_port_bindings, installed_port_bindings
from app.trading.assistant_tool import TradingMarketDataTool

from .harness import capture


def _catalog(*tools) -> list[dict]:
    install_port_bindings(PortBindings.build([
        PortBinding(TOOL_DECLARATIONS, tool, owner=tool.tool_id) for tool in tools
    ]))
    rows = [row for row in default_capability_registry().all() if row.namespace != "mcp"]
    return [
        {**row.model_dump(mode="json", exclude={"name", "description"}), "definition_hash": _definition_hash(row)}
        for row in sorted(rows, key=lambda row: row.id)
    ]


def test_tool_catalog_with_all_features_and_without_trading():
    previous = installed_port_bindings()
    try:
        capture("tool-catalog", lambda: {
            "all_features": _catalog(ResearchTool(), TradingMarketDataTool()),
            "trading_disabled": [row["id"] for row in _catalog(ResearchTool())],
        })
    finally:
        install_port_bindings(previous)
