from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def plan_audit_payload(
    *,
    source: str,
    mode: str,
    timestamp: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "mode": mode,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "detail": detail or {},
        "read_only": True,
        "executes": False,
        "review_required": True,
    }
