"""A published world's pressures as the plan its campaign's world clock runs (RQ-4.2).

The causal runtime (``world.causal_runtime``) ticks a pressure plan every turn, but only campaigns
made by the campaign World Forge had one: a campaign launched from a published world started with
no clock. Launch now builds the plan from the world's own ``pressures`` section (RQ-2.0) or, when the
world has none, derives one from what it does say: if creatures roam it, each region's roads are a
danger that grows unless the player fights them back (``defeat:<creature id>`` levers).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.world.causal_runtime import bootstrap_causal_runtime

from .lore_sections import lore_rows
from .world_play_sections import WorldPressure, parse_play_sections

# The bestiary rates threat; the most dangerous creature sets how dangerous a region's roads start.
_THREAT_SEVERITY = {"low": 25.0, "minor": 25.0, "medium": 40.0, "moderate": 40.0, "high": 55.0, "severe": 55.0,
                    "extreme": 70.0, "boss": 70.0, "legendary": 70.0, "mythic": 70.0, "deadly": 70.0}
# How much one turn of a pressure moves the region dimension it bears on.
_REGION_EFFECT_PER_TICK = 1.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def derived_pressures(canon: Mapping[str, Any]) -> tuple[WorldPressure, ...]:
    """Road danger in every region of a world whose bestiary is not empty; nothing for a world without creatures."""
    creatures = [row for row in lore_rows(canon, "bestiary") if _text(row.get("id"))]
    if not creatures:
        return ()
    severity = max(_THREAT_SEVERITY.get(_text(row.get("threat")).casefold(), 40.0) for row in creatures)
    names = ", ".join(_text(row.get("name")) or _text(row.get("id")) for row in creatures[:3])
    pressures = []
    for region in lore_rows(canon, "regions"):
        region_id, name = _text(region.get("id")), _text(region.get("name"))
        if not region_id:
            continue
        pressures.append(
            WorldPressure(
                pressure_id=f"pressure:roads:{region_id.split(':', 1)[-1]}",
                name=f"Danger on the roads of {name or region_id}",
                description=f"{names} prey on travellers; trade suffers while they go unchecked.",
                region_id=region_id,
                dimension="trade_access",
                severity=severity,
                trend="volatile",
                levers=tuple(
                    {"action": f"defeat:{_text(row.get('id'))}", "effect": "lower", "amount": 8.0}
                    for row in creatures
                ),
            )
        )
    return tuple(pressures)


def pressure_planning(canon: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """The planning topics the causal runtime bootstraps from, and whether they are ``authored`` or ``derived``."""
    authored = parse_play_sections(canon)[0].pressures
    pressures = authored or derived_pressures(canon)
    regions: dict[str, dict[str, float]] = {}
    plan = []
    for pressure in pressures:
        regions.setdefault(pressure.region_id, {})[pressure.dimension] = max(0.0, 100.0 - pressure.severity)
        plan.append(
            {
                "pressure_id": pressure.pressure_id,
                "name": pressure.name,
                "summary": pressure.description,
                "severity": pressure.severity,
                "trend": pressure.trend,
                "escalation_threshold": pressure.escalation_threshold,
                "resolution_threshold": pressure.resolution_threshold,
                "next_tick_delta": {
                    "target_id": pressure.region_id,
                    "dimension": pressure.dimension,
                    "operation": "decrease",
                    "value": _REGION_EFFECT_PER_TICK,
                },
                "levers": [lever.model_dump() for lever in pressure.levers],
            }
        )
    planning = {
        "present_day_state": {"state": regions},
        "pressure_plan": {"pressures": plan},
    }
    return planning, "authored" if authored else "derived"


def published_causal_runtime(canon: Mapping[str, Any]) -> dict[str, Any]:
    """The world clock a new campaign starts with; empty when the world has neither pressures nor creatures."""
    planning, source = pressure_planning(canon)
    if not planning["pressure_plan"]["pressures"]:
        return {}
    del source  # the world model's authorship records whether pressures were authored or derived
    return bootstrap_causal_runtime(planning)


__all__ = ["derived_pressures", "pressure_planning", "published_causal_runtime"]
