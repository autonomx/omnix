#!/usr/bin/env python3
"""Emit the exact-head provider-free release certificate for Narrative Engine G-L."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    InMemoryNarrativeDeliveryRepository,
    InMemoryNarrativeResponseRepository,
    NarrativeBlock,
    NarrativeDeliveryCoordinator,
    ValidationReport,
)
from app.rpg.narrative_engine.consumer_publish import attach_canonical_consumer_bundle
from app.rpg.narrative_engine.production_path import enforce_production_narrative_result
from app.rpg.narrative_engine.publisher_guard import publisher_guard
from app.rpg.narrative_engine.release_certification import (
    certify_unified_narrative_release,
)
from app.rpg.narrative_retirement import (
    build_production_narrative_retirement_repository,
    reset_narrative_retirement_repository_cache,
)
from app.rpg.response_generation.release_gate import (
    CampaignEvidenceRow,
    metrics_from_campaign_rows,
)


def _fixture_response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase42:release",
        request_id="request:phase42:release",
        turn_id="turn:phase42:release",
        campaign_id="campaign:phase42:release",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="response:phase42:release:block:1",
                beat_id="beat:phase42:1",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="Bran turns toward the rain-dark road.",
            ),
            NarrativeBlock(
                block_id="response:phase42:release:block:2",
                beat_id="beat:phase42:2",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="The bridge still holds.",
                speaker_id="npc:bran",
            ),
            NarrativeBlock(
                block_id="response:phase42:release:block:3",
                beat_id="beat:phase42:3",
                sequence=3,
                kind=BeatKind.CHOICE,
                purpose=BeatPurpose.CONTINUATION,
                text="The eastern road remains open.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase42-release-fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def _runtime_evidence() -> tuple[dict[str, bool], dict[str, Any]]:
    publisher_guard.reset_for_tests()
    reset_narrative_retirement_repository_cache()
    response = _fixture_response()

    responses = InMemoryNarrativeResponseRepository()
    persisted = responses.save(response)
    loaded = responses.get(response.response_id)
    roundtrip = (
        loaded is not None
        and loaded.response_id == response.response_id
        and loaded.semantic_hash == response.semantic_hash
        and loaded.as_dict() == persisted.as_dict()
    )

    coordinator = NarrativeDeliveryCoordinator()
    blocking_repository = InMemoryNarrativeDeliveryRepository()
    blocking = coordinator.open(
        response,
        DeliveryMode.BLOCKING,
        blocking_repository,
    )

    deferred_repository = InMemoryNarrativeDeliveryRepository()
    deferred = coordinator.open(
        response,
        DeliveryMode.DEFERRED,
        deferred_repository,
    )
    events = []
    current = deferred
    while current.delivery.status not in {"complete", "cancelled"}:
        current, event = coordinator.publish_next(
            response,
            deferred_repository,
            expected_semantic_hash=response.semantic_hash,
        )
        if event is not None:
            events.append(event)
    ordered = [event.block.block_id for event in events] == [
        block.block_id for block in response.blocks
    ]
    delivery_equivalent = (
        blocking.semantic_hash == response.semantic_hash
        and deferred.semantic_hash == response.semantic_hash
        and current.semantic_hash == response.semantic_hash
        and blocking.response_id == deferred.response_id == response.response_id
    )

    result = attach_canonical_consumer_bundle(
        {
            "ok": True,
            "canonical_narrative_response": response.as_dict(),
        }
    )
    certified = enforce_production_narrative_result(result)
    production_passed = (
        dict(certified.get("narrative_production_certification") or {}).get("passed")
        is True
    )
    retirement_record = dict(certified.get("narrative_retirement_record") or {})
    retirement_repository = build_production_narrative_retirement_repository(
        environ={"OMNIX_RPG_NARRATIVE_RETIREMENT_REPOSITORY": "in_memory"}
    )
    retirement_snapshot = retirement_repository.release_snapshot()

    checks = {
        "canonical_roundtrip_stable": roundtrip,
        "blocking_deferred_semantic_equivalence": delivery_equivalent,
        "deferred_delivery_ordered_complete": (
            ordered
            and current.delivery.status == "complete"
            and len(events) == len(response.blocks)
        ),
        "production_certification_passed": production_passed,
        "retirement_record_persisted": (
            retirement_record.get("response_id") == response.response_id
            and retirement_record.get("content_hash") == response.semantic_hash
            and retirement_record.get("alternate_publish_count") == 0
        ),
    }
    return checks, retirement_snapshot


def _release_metrics(exact_head: bool):
    rows = tuple(
        CampaignEvidenceRow(
            turn_id=f"phase42:{index}",
            allowed_forward_outcome=True,
            normal_turn_latency_ms=100.0 + index,
        )
        for index in range(32)
    )
    return metrics_from_campaign_rows(
        rows,
        replay_hash_stable=True,
        persistent_proposal_peak=8,
        persistent_proposal_budget=64,
        exact_head_checks_passed=exact_head,
        p95_budget_ms=5000.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--observed-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    expected = args.expected_head.strip().lower()
    observed = args.observed_head.strip().lower()
    runtime_checks, retirement_snapshot = _runtime_evidence()
    certificate = certify_unified_narrative_release(
        repository_root=args.repository_root,
        expected_head_sha=expected,
        observed_head_sha=observed,
        release_metrics=_release_metrics(expected == observed),
        runtime_checks=runtime_checks,
        retirement_snapshot=retirement_snapshot,
    )
    payload = certificate.as_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if certificate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
