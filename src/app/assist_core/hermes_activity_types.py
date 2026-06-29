from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HermesActivityItem:
    timestamp: str
    source: str
    summary: str
    names: list[str] = field(default_factory=list)
    dry_run: bool = True
    ok: bool | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def hermes_activity_item_payload(item: HermesActivityItem) -> dict[str, Any]:
    return asdict(item)


def hermes_activity_list_payload(items: list[HermesActivityItem] | None = None) -> dict[str, Any]:
    rows = [hermes_activity_item_payload(item) for item in items or []]
    return {"ok": True, "items": rows, "count": len(rows)}
