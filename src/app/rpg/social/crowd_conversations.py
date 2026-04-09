from __future__ import annotations

from typing import Any, Dict, List


def build_background_chatter_lines(location_id: str, recent_events: List[Dict[str, Any]]) -> List[str]:
    if recent_events:
        return ["The crowd murmurs about what just happened."]
    return []
