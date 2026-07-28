from __future__ import annotations

from app.rpg.worlds.generation_starting_market import (
    require_valid_starting_market,
    starting_market_report,
)


def test_starting_market_gate_skips_graphs_without_declared_contract() -> None:
    graph = {
        "metadata": {},
        "nodes": [
            {
                "topic_id": "setting_rules",
                "metadata": {"field_definitions": []},
            }
        ],
    }

    report = starting_market_report([], graph)
    require_valid_starting_market([], graph)

    assert report["passed"] is True
    assert report["materialization"]["contract_enabled"] is False
    assert report["materialization"]["skipped"] is True
    assert report["issues"] == []
