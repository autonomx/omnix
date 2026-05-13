from __future__ import annotations

from typing import List

from app.rpg.economy.economy_pressure import EconomyPressureRule


def tavern_economy_pressure_rules() -> List[EconomyPressureRule]:
    return [
        EconomyPressureRule(
            id="economy:daily_lodging",
            kind="lodging_upkeep",
            every_turns=24,
            cost_currency=("gold", 1),
            warning_threshold_currency=("gold", 3),
            cooldown_turns=20,
            event={
                "summary": "Daily lodging upkeep comes due at the Rusty Flagon.",
            },
            world_signal={
                "id": "signal:economy_lodging_due",
                "scope": "scene:rusty_flagon",
                "summary": "Lodging costs continue to matter during the investigation.",
                "intensity": 1,
            },
        ),
        EconomyPressureRule(
            id="economy:food_and_supplies",
            kind="food_supply_upkeep",
            every_turns=18,
            cost_currency=("copper", 5),
            warning_threshold_currency=("copper", 10),
            cooldown_turns=12,
            event={
                "summary": "Food, candles, and small supplies drain coin.",
            },
            world_signal={
                "id": "signal:economy_supplies_drain",
                "scope": "scene:rusty_flagon",
                "summary": "Small supplies are being consumed as the days pass.",
                "intensity": 1,
            },
        ),
        EconomyPressureRule(
            id="economy:road_risk_surcharge",
            kind="travel_surcharge",
            every_turns=30,
            cost_currency=("gold", 1),
            warning_threshold_currency=("gold", 2),
            cooldown_turns=20,
            event={
                "summary": "Road risk raises the cost of travel and resupply.",
            },
            world_signal={
                "id": "signal:economy_road_surcharge",
                "scope": "region:mill_road",
                "summary": "Merchants raise prices while road pressure remains high.",
                "intensity": 2,
            },
        ),
    ]