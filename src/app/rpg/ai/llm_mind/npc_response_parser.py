from __future__ import annotations

from typing import Any, Dict


class NPCResponseParser:
    def parse_decision(self, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        return {}
