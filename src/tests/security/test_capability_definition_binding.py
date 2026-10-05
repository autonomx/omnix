"""Approvals are bound to the capability definition they were issued for (PA-1.4)."""
from __future__ import annotations

import pytest

from app.platform.agent_runtime.broker_api import approval_definition_refusal
from app.platform.agent_runtime.contracts import AgentApproval
from app.capabilities import registry
from app.capabilities.registry import (
    DISPLAY_ONLY_CAPABILITY_FIELDS,
    Capability,
    _definition_hash,
    capability_catalog_digest,
    capability_definition_hash,
)

# Every field outside DISPLAY_ONLY_CAPABILITY_FIELDS is in the definition hash.
# A new Capability field fails this test until someone decides, with review,
# whether it bounds authority (then add it here) or only describes it.
AUTHORITY_FIELDS = {
    "id", "namespace", "execution_zone", "effect", "risk", "scope_type", "approval_policy",
    "network_required", "credential_required", "audited", "enabled", "requires_connection",
    "requires_confirmation", "destructive", "provider", "input_schema", "output_schema",
}


def test_every_capability_field_is_classified():
    assert set(Capability.model_fields) == AUTHORITY_FIELDS | DISPLAY_ONLY_CAPABILITY_FIELDS
    assert not AUTHORITY_FIELDS & DISPLAY_ONLY_CAPABILITY_FIELDS


def _row(**changes):
    base = registry.capability("example.read", "Read", "Reads.", zone="broker", effect="read")
    return base.model_copy(update=changes)


@pytest.mark.parametrize("field,value", [
    ("risk", "high"), ("scope_type", "global"), ("approval_policy", "always_ask"), ("destructive", True),
    ("provider", "Other backend"), ("enabled", False), ("input_schema", {"x": "y"}),
])
def test_authority_fields_change_the_hash(field, value):
    assert _definition_hash(_row(**{field: value})) != _definition_hash(_row())


@pytest.mark.parametrize("field,value", [
    ("name", "Other"), ("description", "Other."), ("category", "other"), ("hermes_visible", True),
])
def test_display_fields_do_not_change_the_hash(field, value):
    assert _definition_hash(_row(**{field: value})) == _definition_hash(_row())


def test_unknown_capabilities_have_no_definition():
    assert capability_definition_hash("no.such_capability") is None
    assert len(capability_definition_hash("workspace.read") or "") == 64
    assert capability_catalog_digest() == capability_catalog_digest()


def _approval(**changes):
    approval = AgentApproval(run_id="run", capability_id="workspace.command", state="approved")
    if "capability_definition_hash" in changes:
        return approval.with_definition_hash(changes["capability_definition_hash"])
    return approval


def test_an_agent_approval_records_its_definition_and_authorizes_while_it_holds():
    approval = _approval()
    assert approval.capability_definition_hash == capability_definition_hash("workspace.command")
    assert approval_definition_refusal(approval) is None


def test_agent_approvals_refuse_unbound_changed_and_missing_definitions(monkeypatch):
    assert approval_definition_refusal(_approval(capability_definition_hash=None)) == "approval_definition_unbound"
    assert approval_definition_refusal(_approval(capability_definition_hash="0" * 64)) == "capability_definition_changed"
    monkeypatch.setattr("app.platform.agent_runtime.broker_api.capability_definition_hash", lambda _capability_id: None)
    assert approval_definition_refusal(_approval()) == "capability_unavailable"


def test_the_definition_hash_stays_out_of_the_api_schema():
    approval = AgentApproval(run_id="run", capability_id="workspace.command")
    assert "capability_definition_hash" not in AgentApproval.model_json_schema()["properties"]
    assert "capability_definition_hash" not in approval.model_dump()
    assert approval.model_copy().capability_definition_hash == approval.capability_definition_hash
