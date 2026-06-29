from __future__ import annotations

from typing import Any

HERMES_RESPONSE_MAX_BYTES = 64_000
HERMES_TIMEOUT_MIN_SECONDS = 1.0
HERMES_TIMEOUT_MAX_SECONDS = 45.0
HERMES_FEATURE_FLAGS = {
    "hermes_enabled": False,
    "agent_chat_enabled": False,
    "proposals_enabled": False,
    "approvals_enabled": False,
    "mutable_actions_enabled": False,
}


def hermes_hardening_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "response_max_bytes": HERMES_RESPONSE_MAX_BYTES,
        "timeout_min_seconds": HERMES_TIMEOUT_MIN_SECONDS,
        "timeout_max_seconds": HERMES_TIMEOUT_MAX_SECONDS,
        "feature_flags": dict(HERMES_FEATURE_FLAGS),
        "blocked_by_default": True,
    }


def hermes_response_size_ok(payload: str) -> bool:
    return len(payload.encode("utf-8")) <= HERMES_RESPONSE_MAX_BYTES
