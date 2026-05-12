from __future__ import annotations

from typing import List

from app.rpg.story.faction_pressure import FactionPressureRule


def tavern_faction_pressure_rules() -> List[FactionPressureRule]:
    return [
        FactionPressureRule(
            id="pressure:sable_chain_suspicious_watchers",
            faction_id="faction:sable_chain",
            min_reputation=-10,
            max_reputation=-2,
            required_tier="suspicious",
            cooldown_turns=12,
            pressure_event={
                "type": "faction_pressure",
                "subtype": "watchers",
                "faction_id": "faction:sable_chain",
                "summary": "Sable Chain watchers begin asking questions along the mill road.",
                "severity": 2,
            },
            world_signal={
                "id": "signal:sable_chain_watchers",
                "kind": "faction_pressure",
                "scope": "region:mill_road",
                "summary": "Travelers notice quiet watchers asking after the party.",
                "ttl_turns": 30,
                "intensity": 2,
            },
            set_flags=("pressure:sable_chain_watchers.active",),
        ),
        FactionPressureRule(
            id="pressure:locals_friendly_support",
            faction_id="faction:rusty_flagon_locals",
            min_reputation=2,
            max_reputation=10,
            required_tier="friendly",
            cooldown_turns=15,
            pressure_event={
                "type": "faction_pressure",
                "subtype": "local_support",
                "faction_id": "faction:rusty_flagon_locals",
                "summary": "Rusty Flagon locals quietly offer useful rumors after the party's help.",
                "severity": 1,
            },
            world_signal={
                "id": "signal:locals_offer_rumors",
                "kind": "support",
                "scope": "scene:rusty_flagon",
                "summary": "Locals are more willing to share rumors with the party.",
                "ttl_turns": 30,
                "intensity": 1,
            },
            set_flags=("pressure:locals_support.active",),
        ),
    ]