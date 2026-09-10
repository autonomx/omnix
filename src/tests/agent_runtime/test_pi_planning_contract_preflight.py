from __future__ import annotations

from pathlib import Path


BROKER = Path(__file__).parents[2] / "app" / "agent_runtime" / "pi_broker_extension.ts"


def _source() -> str:
    return BROKER.read_text(encoding="utf-8")


def test_submit_and_amend_preflight_current_planning_authority() -> None:
    source = _source()

    assert "/planning/inspect" in source
    assert 'body: JSON.stringify({ queries: [], paths: [] })' in source
    assert 'action === "submit" || action === "amend"' in source
    assert "planningReferenceMismatch(params.plan || {}, inspection)" in source
    assert "planning_contract_reference_mismatch" in source


def test_preflight_rejects_invented_requirement_and_candidate_ids() -> None:
    source = _source()

    assert "validRequirementIds" in source
    assert "validCandidateIds" in source
    assert "referencedRequirementIds" in source
    assert "referencedCandidateIds" in source
    assert "invalid_requirement_ids" in source
    assert "invalid_candidate_ids" in source
    assert "requirement_coverage" in source
    assert "change?.requirement_ids" in source
    assert "change?.candidate_ids" in source
    assert "validation?.requirement_ids" in source


def test_empty_candidate_contract_tells_pi_not_to_invent_candidate_aliases() -> None:
    source = _source()

    assert "impact_candidates is empty, so omit impacts and every candidate_ids field" in source
    assert "C1/C2-style" in source
    assert "never substitute paths" in source
    assert "resubmit immediately" in source.lower()
    assert "do not perform more repository inspection merely to repair this contract mismatch" in source.lower()


def test_preflight_does_not_replace_server_authority_when_inspection_is_unavailable() -> None:
    source = _source()

    assert "Server-side planning gates remain authoritative" in source
    inspection_block = source.split("const planningInspection", 1)[1].split("const planningReferenceMismatch", 1)[0]
    assert "return null" in inspection_block
    execute_block = source.split("async execute(_toolCallId, params, signal)", 1)[1]
    assert "const response = await fetch" in execute_block
