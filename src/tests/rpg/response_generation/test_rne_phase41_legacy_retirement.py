from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
)
from app.rpg.narrative_engine.consumer_publish import attach_canonical_consumer_bundle
from app.rpg.narrative_engine.legacy_retirement import (
    audit_legacy_publisher_retirement,
    production_legacy_retirement_audit,
    reset_legacy_retirement_audit_cache,
)
from app.rpg.narrative_engine.production_path import (
    NarrativeProductionPathError,
    enforce_production_narrative_result,
)
from app.rpg.narrative_engine.publisher_guard import publisher_guard
from app.rpg.narrative_retirement import (
    InMemoryNarrativeRetirementRepository,
    reset_narrative_retirement_repository_cache,
)


ROOT = Path(__file__).resolve().parents[4]


def _response(response_id: str = "response:phase41") -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id=response_id,
        request_id=f"request:{response_id}",
        turn_id=f"turn:{response_id}",
        campaign_id="campaign:phase41",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id=f"{response_id}:block",
                beat_id="beat:phase41",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.CONTINUATION,
                text="Only the canonical response crosses the publication boundary.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase41-fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def _canonical_result(response_id: str = "response:phase41") -> dict:
    return attach_canonical_consumer_bundle(
        {
            "ok": True,
            "canonical_narrative_response": _response(response_id).as_dict(),
        }
    )


def setup_function() -> None:
    publisher_guard.reset_for_tests()
    reset_narrative_retirement_repository_cache()
    reset_legacy_retirement_audit_cache()


def teardown_function() -> None:
    publisher_guard.reset_for_tests()
    reset_narrative_retirement_repository_cache()
    reset_legacy_retirement_audit_cache()


def test_production_legacy_deletion_audit_has_no_retired_owner_imports() -> None:
    audit = production_legacy_retirement_audit()
    assert audit.passed is True, audit.as_dict()
    assert audit.forbidden_hits == {}
    assert audit.checks["retired_imports_deleted_from_production_owners"] is True
    assert audit.checks["bridge_marks_legacy_prose_unconsumed"] is True
    assert audit.as_dict()["legacy_publisher_deletion_certified"] is True
    assert "src/app/rpg/response_generation/legacy_bridge.py" in (
        audit.compatibility_only_paths
    )


def test_static_audit_fails_when_retired_publisher_reenters_gateway(tmp_path) -> None:
    for relative in (
        "src/app/gateway/rpg_turn_pipeline.py",
        "src/app/rpg/session/turn_presenter.py",
        "src/app/rpg/session/narrative_engine_bridge.py",
        "src/app/rpg/narrative_engine/consumer_publish.py",
        "src/app/rpg/narrative_engine/production_path.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        source = "present_authoritative_turn()\nattach_canonical_consumer_bundle()\n"
        source += "TurnPresentationInvariantError\nturn_presentation_request_count\n"
        source += 'result["legacy_visible_prose_consumed"] = False\n'
        source += "publish_canonical_bundle()\n"
        source += 'result["legacy_compatibility_fields_source"] = "canonical_projection_only"\n'
        source += "NarrativeProductionPathError\nif not certification.passed\n"
        path.write_text(source, encoding="utf-8")
    gateway = tmp_path / "src/app/gateway/rpg_turn_pipeline.py"
    gateway.write_text(
        gateway.read_text(encoding="utf-8")
        + "\nfrom app.rpg.response_generation.legacy_bridge import play_scene\n",
        encoding="utf-8",
    )

    audit = audit_legacy_publisher_retirement(tmp_path)
    assert audit.passed is False
    assert audit.checks["retired_imports_deleted_from_production_owners"] is False
    assert "src/app/gateway/rpg_turn_pipeline.py" in audit.forbidden_hits


def test_production_enforcement_records_durable_retirement_proof() -> None:
    result = enforce_production_narrative_result(_canonical_result())
    record = result["narrative_retirement_record"]
    assert result["legacy_publisher_deletion_certified"] is True
    assert result["legacy_publisher_deletion_audit"]["passed"] is True
    assert record["response_id"] == "response:phase41"
    assert record["publisher"] == "unified_narrative_engine_v1"
    assert record["alternate_publish_count"] == 0
    assert record["legacy_ownership_retired"] is True
    assert record["compatibility_projection_only"] is True
    assert record["production_certification"]["passed"] is True


def test_alternate_publication_telemetry_prevents_retirement_certification() -> None:
    with pytest.raises(Exception, match="alternate RPG narrative publisher rejected"):
        publisher_guard.publish(
            publisher="legacy_scene_narrator",
            response_id="response:legacy",
            content_hash="sha256:legacy",
            payload={},
        )
    result = _canonical_result("response:phase41:rejected")
    assert result["narrative_publisher_telemetry"]["alternate_publish_count"] == 1
    with pytest.raises(
        NarrativeProductionPathError,
        match="zero_alternate_publishers",
    ):
        enforce_production_narrative_result(result)


def test_retirement_repository_release_snapshot_requires_real_records() -> None:
    repository = InMemoryNarrativeRetirementRepository()
    empty = repository.release_snapshot()
    assert empty["legacy_publisher_deletion_certified"] is False

    audit = production_legacy_retirement_audit().as_dict()
    repository.put(
        response_id="response:phase41:repo",
        content_hash="sha256:phase41",
        publisher="unified_narrative_engine_v1",
        canonical_publish_count=1,
        alternate_publish_count=0,
        rejected_alternate_count=0,
        legacy_ownership_retired=True,
        compatibility_projection_only=True,
        delivery_mode="blocking",
        production_certification={"passed": True},
        deletion_audit=audit,
        metadata={},
    )
    snapshot = repository.release_snapshot()
    assert snapshot["record_count"] == 1
    assert snapshot["zero_alternate_publishers"] is True
    assert snapshot["legacy_publisher_deletion_certified"] is True


def test_phase41_source_guards_cover_durable_records_and_fail_closed_enforcement() -> None:
    migration = (
        ROOT
        / "src"
        / "app"
        / "persistence"
        / "migrations"
        / "0023_rpg_narrative_retirement.sql"
    ).read_text(encoding="utf-8")
    production = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "narrative_engine"
        / "production_path.py"
    ).read_text(encoding="utf-8")
    retirement = (
        ROOT / "src" / "app" / "rpg" / "narrative_retirement.py"
    ).read_text(encoding="utf-8")

    assert "omnix_rpg_narrative_retirement_records" in migration
    assert "alternate_publish_count" in migration
    assert "deletion_audit_jsonb" in migration
    assert "record_narrative_retirement(retired)" in production
    assert "retirement proof failed" in production
    assert "production_legacy_retirement_audit()" in retirement
    assert "legacy_publisher_deletion_certified" in retirement
