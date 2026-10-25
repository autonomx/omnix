"""Canonical evidence and operating policy for the interactive RPG response release."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INTERACTIVE_RELEASE_VERSION = "rpg_interactive_response_release_v1"
LOCAL_LIVE_SMOKE_ENV = "OMNIX_RPG_LIVE_SMOKE"
TARGET_DIALOGUE_MEDIAN_SECONDS = 1.5
TARGET_DIALOGUE_P95_SECONDS = 2.5
MAX_BROWSER_COMMIT_VISIBLE_MS = 50.0


@dataclass(frozen=True)
class ReleasePhaseEvidence:
    phase: int
    title: str
    pull_request: int
    exact_head_sha: str
    merge_sha: str
    provider_free_ci: bool = True


def local_live_acceptance_criteria() -> dict[str, Any]:
    return {
        "format_version": INTERACTIVE_RELEASE_VERSION,
        "minimum_distinct_interactions": 3,
        "same_submission_replay_must_match_interaction_id": True,
        "maximum_turn_response_bytes": 50_000,
        "required_contract_version": "rpg_turn_response_v2",
        "required_visible_text": True,
        "required_monotonic_interaction_ids": True,
        "target_median_seconds": TARGET_DIALOGUE_MEDIAN_SECONDS,
        "target_p95_seconds": TARGET_DIALOGUE_P95_SECONDS,
        "maximum_browser_commit_visible_ms": MAX_BROWSER_COMMIT_VISIBLE_MS,
        "target_is_operator_evidence_not_ci_assertion": True,
    }
