from __future__ import annotations

from copy import deepcopy

import pytest

from app.rpg.worlds.contracts import WorldRevisionDocument
from app.rpg.worlds.revision_authorship import require_revision_authorship
from app.rpg.worlds.service import compile_world_revision


@pytest.fixture(autouse=True)
def production_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OMNIX_RPG_AUTHORSHIP_SIGNING_KEY",
        "test-only-world-revision-signing-key-with-more-than-thirty-two-bytes",
    )
    monkeypatch.delenv("RPG_TEST_MODE", raising=False)


def _revision() -> WorldRevisionDocument:
    return compile_world_revision(
        world_id="world:new",
        revision=1,
        title="New World",
        canon={"summary": "A newly generated world with signed publication lineage."},
        entity_manifest={"entities": {}},
        topology={"locations": [], "routes": []},
        provenance={
            "source": "durable_world_generation",
            "generation_run_id": "run:new",
            "topic_hashes": {"setting_rules": "sha256:setting-rules"},
        },
    )


def test_generated_revision_receipt_is_signed_and_verified() -> None:
    revision = _revision()
    receipt = require_revision_authorship(revision)
    assert receipt["publishable"] is True
    assert receipt["server_signature_verified"] is True
    assert receipt["generation_run_id"] == "run:new"


def test_generated_revision_receipt_tampering_is_rejected() -> None:
    revision = _revision()
    payload = revision.model_dump(mode="json")
    payload = deepcopy(payload)
    payload["provenance"]["authorship_receipt"]["generation_run_id"] = "run:forged"
    tampered = WorldRevisionDocument.model_validate(payload)
    with pytest.raises(
        ValueError,
        match="world_revision_generation_receipt_signature_invalid",
    ):
        require_revision_authorship(tampered)


def test_unsigned_generated_revision_is_rejected_in_production() -> None:
    revision = WorldRevisionDocument(
        world_id="world:unsigned",
        revision=1,
        title="Unsigned World",
        canon={"summary": "Unsigned generated text."},
        provenance={
            "source": "durable_world_generation",
            "generation_run_id": "run:unsigned",
            "topic_hashes": {"setting_rules": "sha256:unsigned"},
        },
    )
    with pytest.raises(
        ValueError,
        match="world_revision_generation_receipt_signature_invalid",
    ):
        require_revision_authorship(revision)
