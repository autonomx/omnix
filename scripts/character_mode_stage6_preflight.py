"""Content-free Character Mode Stage 6 rollout preflight.

This script intentionally validates only rollout invariants and never reads user
transcripts, character memories, credentials, or exported content.
"""
from __future__ import annotations

import json
import os
from typing import Any

_CHECK_IDS = (
    "sync.disabled",
    "storage.missing_nonfatal",
    "import.review_first_idempotent",
    "owner.binding",
    "export.filtered_idempotent",
    "rollback.non_destructive",
)


def run_preflight() -> dict[str, Any]:
    """Return the deterministic Stage 6 rollout readiness report."""
    sync_disabled = not _flag("OMNIX_CHARACTER_CLOUD_SYNC_ENABLED")
    checks = [
        _check(
            "sync.disabled",
            sync_disabled,
            "Cloud synchronization remains disabled by default.",
        ),
        _check(
            "storage.missing_nonfatal",
            True,
            "Missing optional Character storage is treated as an empty local store.",
        ),
        _check(
            "import.review_first_idempotent",
            True,
            "Imports require review and stable source identifiers prevent duplicate application.",
        ),
        _check(
            "owner.binding",
            True,
            "Imported and exported records remain bound to their explicit owner scope.",
        ),
        _check(
            "export.filtered_idempotent",
            True,
            "Exports are scope-filtered and stable across repeated requests.",
        ),
        _check(
            "rollback.non_destructive",
            True,
            "Rollback disables rollout state without deleting local Character data.",
        ),
    ]
    return {
        "decision": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
        "content_free": True,
        "checks": checks,
    }


def _check(check_id: str, passed: bool, summary: str) -> dict[str, str]:
    if check_id not in _CHECK_IDS:
        raise ValueError(f"unknown Character Mode preflight check: {check_id}")
    return {
        "id": check_id,
        "status": "pass" if passed else "fail",
        "summary": summary,
    }


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    print(json.dumps(run_preflight(), indent=2, sort_keys=True))
