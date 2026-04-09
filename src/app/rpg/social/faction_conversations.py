from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_faction_topic_candidates(simulation_state: Dict[str, Any], faction_id: str) -> List[Dict[str, Any]]:
    return [{
        "type": "faction_tension",
        "anchor": f"faction:{faction_id}",
        "summary": "Faction members debate their next move.",
        "stance": "plan",
        "priority": 0.80,
    }]
