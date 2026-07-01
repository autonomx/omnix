from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = frozenset({"secret", "token", "api_key", "password"})


def redact_plan_audit_detail(detail: dict[str, Any], max_length: int = 80) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in detail.items():
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = "[redacted]"
            continue
        if isinstance(value, str) and len(value) > max_length:
            redacted[key] = f"{value[:max_length]}..."
            continue
        redacted[key] = value
    return redacted
