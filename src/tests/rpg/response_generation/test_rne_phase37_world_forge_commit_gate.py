from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from app.rpg.session.genesis.canon_audit import (
    CanonAuditIssue,
    CanonAuditReport,
)
from app.rpg.session.genesis.compiler import compile_campaign_genesis
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.materialization import (
    materialize_world_forge_into_session,
    persist_campaign_genesis,
)
from app.rpg.session.genesis.world_forge_commit import (
    WorldForgeCommitBlockedError,
    certify_world_forge_commit,
    require_world_forge_commit_ready,
)
from app.rpg.session.genesis.world_forge_default import (
    ReferenceSafeWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_pipeline import run_campaign_world_forge


ROOT = Path(__file__).resolve().parents[4]


def _contract() -> CampaignGenesisContract:
    return CampaignGenesisContract.model_validate(
        {
            "campaign_template": "classic_fantasy",
            "genre": "fantasy",
            "tone": "grounded adventure",
            "world_options": {
                "starting_location": "rusty_flagon_tavern",
                "difficulty": "normal",
                "world_activity": "living_world",
                "economy_pressure": "normal",
                "combat_lethality": "normal",
                "seed": 37,
            },
            "world_forge": {
                "depth": "standard",
                "background_expansion": False,
                "require_consistency_audit": True,
                "require_opening_dossiers": True,
            },
        }
    )


def _world_forge():
    contract = _contract()
    return contract, run_campaign_world_forge(
        contract,
        campaign_id="campaign:phase37",
        compiled_genesis=compile_campaign_genesis(contract),
        generator=ReferenceSafeWorldForgeGenerator(),
    )


def _failed_world_forge():
    contract, result = _world_forge()
    failed_audit = CanonAuditReport(
        passed=False,
        issues=(
            CanonAuditIssue(
                code="phase37_injected_failure",
                message="Injected audit failure must block canon commit.",
            ),
        ),
        checks={"errors": 1},
    )
    return contract, replace(result, audit=failed_audit)


def _session() -> dict:
    return {
        "manifest": {
            "session_id": "campaign:phase37",
            "title": "Phase 37",
        },
        "state": {"title": "Phase 37"},
        "runtime_state": {},
        "setup_payload": {},
    }


def test_valid_world_forge_result_receives_stable_commit_certification() -> None:
    _contract_value, world_forge = _world_forge()
    certification = certify_world_forge_commit(world_forge)

    assert certification.passed is True
    assert certification.errors == ()
    assert certification.content_hash.startswith("sha256:")
    assert certification.content_hash == world_forge.compilation.document["content_hash"]
    assert all(certification.checks.values())


def test_failed_audit_blocks_authoritative_commit() -> None:
    _contract_value, world_forge = _failed_world_forge()
    certification = certify_world_forge_commit(world_forge)

    assert certification.passed is False
    assert "audit_passed" in certification.errors
    assert "aggregate_launch_ready" in certification.errors
    with pytest.raises(WorldForgeCommitBlockedError, match="audit_passed"):
        require_world_forge_commit_ready(world_forge)


def test_materialization_rejects_failed_canon_without_touching_session() -> None:
    contract, world_forge = _failed_world_forge()
    session = _session()
    before = deepcopy(session)

    with pytest.raises(WorldForgeCommitBlockedError):
        materialize_world_forge_into_session(session, contract, world_forge)

    assert session == before
    assert "campaign_bible_projection" not in session


def test_persistence_rejects_failed_canon_before_database_access() -> None:
    contract, world_forge = _failed_world_forge()

    with pytest.raises(WorldForgeCommitBlockedError):
        persist_campaign_genesis(
            _session(),
            contract,
            world_forge,
            database=object(),
            required=False,
        )


def test_valid_materialization_records_commit_certification_everywhere() -> None:
    contract, world_forge = _world_forge()
    session = materialize_world_forge_into_session(
        _session(),
        contract,
        world_forge,
    )

    expected_hash = world_forge.compilation.document["content_hash"]
    assert session["manifest"]["campaign_bible_commit_certified"] is True
    assert session["manifest"]["campaign_bible_content_hash"] == expected_hash
    assert session["state"]["campaign_bible"]["commit_certification"]["passed"] is True
    assert session["runtime_state"]["campaign_launch_gate"]["ready"] is True
    assert session["campaign_bible_projection"]["commit_certification"]["passed"] is True


def test_pipeline_certifies_before_materialization_or_persistence() -> None:
    pipeline = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "pipeline_adapter.py"
    ).read_text(encoding="utf-8")
    materialization = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "materialization.py"
    ).read_text(encoding="utf-8")

    certification = pipeline.index("certify_world_forge_commit(world_forge)")
    assert certification < pipeline.index("materialize_world_forge_into_session(")
    assert certification < pipeline.index("persist_campaign_genesis(")
    assert materialization.count("require_world_forge_commit_ready(world_forge)") == 2
    assert '"mode": "rejected_unapproved_canon"' in pipeline
