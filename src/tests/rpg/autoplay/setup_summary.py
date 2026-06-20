"""Small helpers for adding RPG setup status to summary payloads."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any


def compact_setup_summary(value: Mapping[str, object] | None) -> dict[str, Any]:
    data = dict(value or {})
    return {
        "ok": bool(data.get("ok")),
        "source": data.get("source"),
        "status": data.get("status"),
        "required": bool(data.get("required")),
        "detected": bool(data.get("detected")),
        "metadata": dict(data.get("metadata") or {}),
    }


def attach_setup_summary(summary: MutableMapping[str, Any], value: Mapping[str, object] | None) -> dict[str, Any]:
    payload = compact_setup_summary(value)
    summary["setup_summary"] = payload
    health = summary.setdefault("health", {})
    if isinstance(health, MutableMapping):
        health["setup_summary"] = {
            "ok": bool(payload.get("ok")),
            "status": payload.get("status"),
            "required": bool(payload.get("required")),
        }
    return payload
