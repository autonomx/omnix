from decimal import Decimal

from app.apps.trading.llm_reliability_metrics import LLMReliabilityLedger, classify_llm_failure


def test_explicit_output_failure_code_wins_over_detail_text():
    quoted = RuntimeError(
        "ai_shadow_v3_invalid_json:schema;detail=thesis says the open timed out near the circuit"
    )
    assert classify_llm_failure(quoted) == "malformed"
    assert classify_llm_failure(TimeoutError("Claude CLI exceeded 30s")) == "timeout"
    assert (
        classify_llm_failure(RuntimeError("ai_shadow_provider_circuit_open:retry_after_seconds=90"))
        == "circuit_open"
    )


def test_llm_reliability_separates_attempts_from_circuit_suppressions():
    ledger = LLMReliabilityLedger()
    ledger.scheduled("codex", "gpt", 3)
    ledger.attempt("codex", "gpt")
    ledger.failure("codex", "gpt", kind="timeout")
    ledger.failure("codex", "gpt", kind="circuit_open", missed=2)
    snapshot = ledger.snapshot()
    row = snapshot.identities[0]
    assert row.scheduled_opportunities == 3
    assert row.provider_attempts == 1
    assert row.timeouts == 1
    assert row.circuit_open_suppressions == 1
    assert row.missed_evaluations == 3
