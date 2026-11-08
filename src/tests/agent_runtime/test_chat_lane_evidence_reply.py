"""What the person reads when Chat cannot get the current information a question needs."""
from __future__ import annotations

from types import SimpleNamespace

from app.platform.agent_runtime import chat_lane_evidence


def _dumpable(value: dict) -> SimpleNamespace:
    return SimpleNamespace(model_dump=lambda mode="json": value)


def _failure(reason: str, detail: str):
    return chat_lane_evidence._chat_evidence_failure(
        _dumpable({"lane": "chat"}), request_mode=_dumpable({"mode": "auto"}), semantic_task=None,
        semantic_compilation=_dumpable({}), routing_shadow={}, reason=reason, detail=detail,
    )


def test_a_disabled_tool_reads_as_what_to_do_and_keeps_the_detail_for_diagnostics() -> None:
    # What a weather question got on 2026-11-07 with Quick search off and the Weather tool's action disabled.
    detail = "required evidence alternatives are unavailable: weather.current=action_disabled"
    result = _failure("evidence_required_but_unavailable", detail)

    assert "Quick search" in result.content and "Tools" in result.content
    assert "governed" not in result.content and "weather.current" not in result.content
    assert result.metadata["semantic_gate"] == {"accepted": False, "reason": "evidence_required_but_unavailable",
                                                "detail": detail}


def test_each_kind_of_failure_says_what_happened() -> None:
    assert "outside sources" in _failure("external_evidence_forbidden", "x").content
    assert "Which place or thing" in _failure("chat_evidence_subject_unresolved", "x").content
    assert "lookup failed" in _failure("chat_evidence_execution_failed", "boom").content
    assert "boom" not in _failure("chat_evidence_execution_failed", "boom").content
