from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .contracts import RenderedResponse, ResponseRequest, SemanticResponsePlan
from .performance import LatencyTrace
from .truth_lifetime import SoftTruthRecord


_SENSITIVE_KEYS = {
    "raw_prompt",
    "system_prompt",
    "private_memory",
    "hidden_memory",
    "hidden_fact",
    "hidden_facts",
    "hidden_world_log",
    "provider_api_key",
    "credentials",
}


@dataclass(frozen=True)
class ResponseGenerationTrace:
    trace_version: str
    turn_id: str
    raw_player_input: str
    interpreted_intents: tuple[Mapping[str, Any], ...]
    selected_affordance: str
    resolver_result: Mapping[str, Any]
    retrieval_sources: tuple[Mapping[str, Any], ...]
    visibility_decisions: tuple[Mapping[str, Any], ...]
    hermes: Mapping[str, Any]
    recovery_plan: Mapping[str, Any]
    agency: Mapping[str, Any]
    proposals: tuple[Mapping[str, Any], ...]
    claim_ledger: Mapping[str, Any]
    semantic_plan: Mapping[str, Any]
    hard_gates: tuple[Mapping[str, Any], ...]
    candidate_ranking: tuple[Mapping[str, Any], ...]
    quality: Mapping[str, Any]
    response_mode: str
    word_budget: tuple[int, int]
    truth_records: tuple[Mapping[str, Any], ...]
    latency: Mapping[str, Any]
    final_visible_response: str
    profile: Mapping[str, Any]
    rollout: Mapping[str, Any]
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self, *, include_player_input: bool = True) -> dict[str, Any]:
        payload = {
            "trace_version": self.trace_version,
            "turn_id": self.turn_id,
            "raw_player_input": self.raw_player_input if include_player_input else "[redacted]",
            "interpreted_intents": [dict(row) for row in self.interpreted_intents],
            "selected_affordance": self.selected_affordance,
            "resolver_result": _sanitize(self.resolver_result),
            "retrieval_sources": [_sanitize(row) for row in self.retrieval_sources],
            "visibility_decisions": [_sanitize(row) for row in self.visibility_decisions],
            "hermes": _sanitize(self.hermes),
            "recovery_plan": _sanitize(self.recovery_plan),
            "agency": _sanitize(self.agency),
            "proposals": [_sanitize(row) for row in self.proposals],
            "claim_ledger": _sanitize(self.claim_ledger),
            "semantic_plan": _sanitize(self.semantic_plan),
            "hard_gates": [_sanitize(row) for row in self.hard_gates],
            "candidate_ranking": [_sanitize(row) for row in self.candidate_ranking],
            "quality": _sanitize(self.quality),
            "response_mode": self.response_mode,
            "word_budget": list(self.word_budget),
            "truth_records": [_sanitize(row) for row in self.truth_records],
            "latency": _sanitize(self.latency),
            "final_visible_response": self.final_visible_response,
            "profile": _sanitize(self.profile),
            "rollout": _sanitize(self.rollout),
            "extra": _sanitize(self.extra),
        }
        return payload


def build_response_trace(
    request: ResponseRequest,
    rendered: RenderedResponse,
    *,
    interpreted_intents: Iterable[Mapping[str, Any]] = (),
    selected_affordance: str = "",
    resolver_result: Mapping[str, Any] | None = None,
    retrieval_sources: Iterable[Mapping[str, Any]] = (),
    visibility_decisions: Iterable[Mapping[str, Any]] = (),
    hermes: Mapping[str, Any] | None = None,
    recovery_plan: Mapping[str, Any] | None = None,
    proposals: Iterable[Mapping[str, Any]] = (),
    claim_ledger: Mapping[str, Any] | None = None,
    semantic_plan: SemanticResponsePlan | Mapping[str, Any] | None = None,
    candidate_ranking: Iterable[Mapping[str, Any]] = (),
    truth_records: Iterable[SoftTruthRecord | Mapping[str, Any]] = (),
    latency: LatencyTrace | Mapping[str, Any] | None = None,
    rollout: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> ResponseGenerationTrace:
    metadata = dict(rendered.metadata)
    plan_payload = _semantic_plan_payload(semantic_plan)
    truth_payload = tuple(
        row.as_dict() if isinstance(row, SoftTruthRecord) else dict(row)
        for row in truth_records
        if isinstance(row, (SoftTruthRecord, Mapping))
    )
    latency_payload = (
        latency.as_dict()
        if isinstance(latency, LatencyTrace)
        else dict(latency or {})
    )
    agency = {
        "effect": metadata.get("agency_effect", "none"),
        "reversibility": metadata.get("reversibility", "fully_reversible"),
        "player_choice_taken": False,
    }
    return ResponseGenerationTrace(
        trace_version="rpg_response_trace_v1",
        turn_id=request.turn_id,
        raw_player_input=request.player_input,
        interpreted_intents=tuple(dict(row) for row in interpreted_intents),
        selected_affordance=selected_affordance,
        resolver_result=dict(resolver_result or request.authoritative_turn_result),
        retrieval_sources=tuple(dict(row) for row in retrieval_sources),
        visibility_decisions=tuple(dict(row) for row in visibility_decisions),
        hermes=dict(hermes or {}),
        recovery_plan=dict(recovery_plan or {}),
        agency=agency,
        proposals=tuple(dict(row) for row in proposals),
        claim_ledger=dict(claim_ledger or {}),
        semantic_plan=plan_payload,
        hard_gates=tuple(
            dict(row)
            for row in metadata.get("hard_gate_decisions", ())
            if isinstance(row, Mapping)
        ),
        candidate_ranking=tuple(dict(row) for row in candidate_ranking),
        quality=dict(rendered.quality_report),
        response_mode=rendered.mode.value,
        word_budget=rendered.word_budget,
        truth_records=truth_payload,
        latency=latency_payload,
        final_visible_response=rendered.text,
        profile=dict(metadata.get("response_profile") or {}),
        rollout=dict(rollout or {}),
        extra=dict(extra or {}),
    )


def player_state_change_indicators(
    authoritative_deltas: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    deltas = dict(authoritative_deltas or {})
    labels = {
        "currency": "Currency updated",
        "inventory": "Inventory updated",
        "quest": "Journal updated",
        "quest_log": "Journal updated",
        "relationship": "Relationship changed",
        "location": "Location changed",
        "combat": "Combat state changed",
        "discovery": "New clue discovered",
    }
    rows: list[dict[str, Any]] = []
    for key in sorted(deltas):
        normalized = str(key).casefold().replace("_delta", "")
        label = next(
            (value for prefix, value in labels.items() if normalized.startswith(prefix)),
            "State updated",
        )
        rows.append({"kind": normalized, "label": label})
    return tuple(rows)


def _semantic_plan_payload(
    value: SemanticResponsePlan | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {
        "mode": value.mode.value,
        "forward_strategy": value.forward_strategy,
        "agency_effect": value.agency_effect.value,
        "reversibility": value.reversibility.value,
        "proposal_refs": list(value.proposal_refs),
        "sections": [
            {
                "section_id": section.section_id,
                "section_type": section.section_type.value,
                "speaker_id": section.speaker_id,
                "claim_refs": list(section.claim_refs),
                "soft_truth_refs": list(section.soft_truth_refs),
                "proposal_refs": list(section.proposal_refs),
            }
            for section in value.sections
        ],
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in _SENSITIVE_KEYS or normalized.startswith("hidden_"):
                continue
            if normalized == "visibility" and str(item).casefold() == "hidden":
                return {"visibility": "hidden", "redacted": True}
            result[str(key)] = _sanitize(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
