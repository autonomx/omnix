from __future__ import annotations

from app.rpg.worlds.generation_starting_market import starting_market_report


def _topic(topic_id: str, entities: list[dict]) -> dict:
    return {
        "topic_id": topic_id,
        "candidate": {
            "topic_id": topic_id,
            "documents": [],
            "entities": entities,
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        },
    }


def _graph() -> dict:
    return {
        "metadata": {"starting_location": "ent:place:1"},
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": []}},
            {
                "topic_id": "actors",
                "metadata": {
                    "field_definitions": [
                        {
                            "field_id": "vendor_inventory_item_ids",
                            "value_type": "entity_ref_list",
                            "allowed_target_domains": ["equipment_vehicles"],
                        }
                    ]
                },
            },
            {
                "topic_id": "equipment_vehicles",
                "metadata": {"field_definitions": []},
            },
        ],
    }


def _rows(
    *,
    price_level: str,
    supply_reliability: str,
    scarcity_level: str,
    reserve_horizon: str,
) -> list[dict]:
    return [
        _topic(
            "places",
            [
                {
                    "id": "ent:place:1",
                    "name": "Copper Market",
                    "local_market_signature": {
                        "price_level": price_level,
                        "supply_reliability": supply_reliability,
                        "shock_sensitivity": "route_sensitive",
                    },
                    "economic_scale_signature": {
                        "scarcity_level": scarcity_level,
                        "reserve_horizon": reserve_horizon,
                        "price_basis": "scarcity_markup",
                        "demand_pressure": "surging",
                    },
                }
            ],
        ),
        _topic(
            "equipment_vehicles",
            [{"id": "ent:item:1", "name": "Field Ration"}],
        ),
        _topic(
            "actors",
            [
                {
                    "id": "ent:actor:1",
                    "location_id": "ent:place:1",
                    "vendor_inventory_item_ids": ["ent:item:1"],
                }
            ],
        ),
    ]


def _item(report: dict) -> dict:
    return report["materialization"]["vendors"][0]["inventory"][0]


def test_crisis_scarcity_raises_price_and_reduces_stock() -> None:
    stable = starting_market_report(
        _rows(
            price_level="stable",
            supply_reliability="robust",
            scarcity_level="abundant",
            reserve_horizon="months",
        ),
        _graph(),
    )
    crisis = starting_market_report(
        _rows(
            price_level="crisis",
            supply_reliability="rationed",
            scarcity_level="critical",
            reserve_horizon="hours",
        ),
        _graph(),
    )

    assert stable["passed"] is True
    assert crisis["passed"] is True
    stable_item = _item(stable)
    crisis_item = _item(crisis)
    assert crisis_item["price"] > stable_item["price"]
    assert crisis_item["quantity"] < stable_item["quantity"]
    basis = crisis_item["economic_basis"]
    assert basis["pricing"]["price_level"] == "crisis"
    assert basis["pricing"]["scarcity_level"] == "critical"
    assert basis["pricing"]["item_category"] == "staple"
    assert basis["stock"]["supply_reliability"] == "rationed"
    assert basis["stock"]["reserve_horizon"] == "hours"


def test_missing_economic_signatures_use_explicit_bounded_defaults() -> None:
    rows = _rows(
        price_level="stable",
        supply_reliability="intermittent",
        scarcity_level="stable",
        reserve_horizon="weeks",
    )
    place = rows[0]["candidate"]["entities"][0]
    place.pop("local_market_signature")
    place.pop("economic_scale_signature")

    first = starting_market_report(rows, _graph())
    second = starting_market_report(rows, _graph())

    assert first == second
    assert first["passed"] is True
    assert first["materialization"]["market_context"] == {
        "price_level": "stable",
        "supply_reliability": "intermittent",
        "shock_sensitivity": "moderate",
        "scarcity_level": "stable",
        "reserve_horizon": "weeks",
        "price_basis": "market_rate",
        "demand_pressure": "steady",
    }
    assert 1 <= _item(first)["quantity"] <= 8
    assert 1 <= _item(first)["price"] <= 9999
