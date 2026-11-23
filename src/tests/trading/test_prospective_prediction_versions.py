"""The prediction versions run in registry order, each after what it consumes, and a freeze records their specs
under the kinds and idempotency suffixes the ledger has always used."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
from pydantic import BaseModel

from app.apps.trading.canonical import canonical_sha256
from app.apps.trading.prospective_gap_repository import ProspectiveGapRecord, ProspectiveGapSessionLedger
from app.apps.trading.prospective_prediction_v41 import DEFAULT_V41_SPEC
from app.apps.trading.prospective_prediction_v42_action import DEFAULT_V42_ACTION_POLICY
from app.apps.trading.prospective_prediction_versions import (
    PREDICTION_VERSIONS,
    V42,
    V43,
    _check_order,
    spec_records,
)


def test_a_freeze_records_each_spec_then_its_action_policy_in_version_order() -> None:
    rows = spec_records()
    assert [(row.instrument_id, row.kind) for row in rows] == [
        ("__research_spec__", "v41_shadow_spec"),
        ("__research_spec_v42__", "v42_shadow_spec"),
        ("__action_spec_v42__", "v42_action_spec"),
        ("__research_spec_v43__", "v43_shadow_spec"),
        ("__action_spec_v43__", "v43_action_spec"),
    ]
    assert rows[0].payload is DEFAULT_V41_SPEC and rows[0].state == DEFAULT_V41_SPEC.activation_state
    assert rows[0].idempotency_suffix == DEFAULT_V41_SPEC.implementation_fingerprint
    assert rows[2].state == "FORWARD_SHADOW_ACTIVE"
    assert rows[2].idempotency_suffix == canonical_sha256(DEFAULT_V42_ACTION_POLICY.model_dump(mode="json"))


def test_a_version_runs_after_the_versions_it_consumes() -> None:
    assert [version.name for version in PREDICTION_VERSIONS] == ["v41", "v42", "v43"]
    assert V43.consumes == ("v42",)
    with pytest.raises(ValueError, match="v43 consumes"):
        _check_order((V43, V42))
    with pytest.raises(ValueError, match="v42 consumes"):
        _check_order((replace(V42, consumes=("v99",)),))


class _Reading(BaseModel):
    value: int


def _record(kind: str, instrument_id: str, value: int, minute: int) -> ProspectiveGapRecord:
    payload = {"value": value}
    return ProspectiveGapRecord(
        session_date=date(2026, 11, 23), cohort_id="c", instrument_id=instrument_id, kind=kind,
        observed_at=datetime(2026, 11, 23, 14, minute, tzinfo=timezone.utc), payload=payload,
        payload_fingerprint=canonical_sha256(payload),
    )


def test_the_ledger_reads_the_latest_record_of_a_kind_as_its_model() -> None:
    ledger = ProspectiveGapSessionLedger(
        session_date=date(2026, 11, 23), session_id="prospective-gap:2026-11-23",
        records=(_record("v42_watch", "AAA", 2, 30), _record("v42_watch", "AAA", 1, 10),
                 _record("v42_watch", "BBB", 9, 50), _record("v43_watch", "AAA", 7, 55)),
    )
    assert ledger.latest_model(_Reading, kind="v42_watch", instrument_id="AAA") == _Reading(value=2)
    assert ledger.latest_model(_Reading, kind="v42_watch") == _Reading(value=9)
    assert ledger.latest_model(_Reading, kind="v42_action", instrument_id="AAA") is None
