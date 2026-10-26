"""The Hermes RPG routes' web contract: their response shapes, as the generated web types read them (split from
``web_contracts``, which kept the play and world routes')."""

from __future__ import annotations

from typing import Any

from typing_extensions import NotRequired, TypedDict


class HermesRpgSequenceStateResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    source: NotRequired[str]
    state: NotRequired[dict[str, Any] | None]
    error: NotRequired[str | None]


class HermesRpgSequenceResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    source: NotRequired[str]
    validation: NotRequired[dict[str, Any]]
    sequence: NotRequired[dict[str, Any]]
    gate: NotRequired[dict[str, Any] | None]
    checkpoint: NotRequired[dict[str, Any] | None]
    loop_guard: NotRequired[dict[str, Any] | None]
    assist_mode: NotRequired[dict[str, Any] | None]
    sequence_state: NotRequired[dict[str, Any] | None]
    state_changed: NotRequired[bool]


class HermesRpgExecutionLedgerItem(TypedDict, total=False):
    execution_id: NotRequired[str]
    created_at: NotRequired[str]
    session_id: NotRequired[str | None]
    sequence_id: NotRequired[str | None]
    item_id: NotRequired[str | None]
    command_text: NotRequired[str | None]
    approval_source: NotRequired[str | None]
    checkpoint_reason: NotRequired[str | None]
    state_changed: NotRequired[bool]
    result_summary: NotRequired[str | None]
    error: NotRequired[str | None]


class HermesRpgExecutionLedgerResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    source: NotRequired[str]
    items: NotRequired[list[HermesRpgExecutionLedgerItem]]
    count: NotRequired[float]


class HermesRpgApprovedFlowConfig(TypedDict, total=False):
    ok: NotRequired[bool]
    source: NotRequired[str]
    feature_flag: NotRequired[str]
    default_enabled: NotRequired[bool]
    enabled: NotRequired[bool]
    requires_payload_enabled: NotRequired[bool]
    simulation_owned: NotRequired[bool]


class HermesRpgApprovedFlowResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    source: NotRequired[str]
    enabled: NotRequired[bool]
    config: NotRequired[HermesRpgApprovedFlowConfig]
    flow: NotRequired[dict[str, Any]]
    readout: NotRequired[dict[str, Any]]
    ledger_entry: NotRequired[dict[str, Any]]
    error: NotRequired[str | None]
    state_changed: NotRequired[bool]


class HermesTestResponseResultResult(TypedDict, total=False):
    response: NotRequired[str]


class HermesTestResponseResult(TypedDict, total=False):
    backend: NotRequired[str]
    result: NotRequired[HermesTestResponseResultResult]


class HermesTestResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    dry_run: NotRequired[bool]
    result: NotRequired[HermesTestResponseResult]
    error: NotRequired[str | None]


class HermesRpgTurnReadoutResponseTurn(TypedDict, total=False):
    turn_id: NotRequired[str | float | None]
    command: NotRequired[str]
    category: NotRequired[str]
    narration_present: NotRequired[bool]


class HermesRpgTurnReadoutResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    read_only: NotRequired[bool]
    source: NotRequired[str]
    session_id: NotRequired[str | None]
    turn: NotRequired[HermesRpgTurnReadoutResponseTurn]
    systems: NotRequired[list[str]]
    effect_count: NotRequired[float]
    grounding_status: NotRequired[str]
    notes: NotRequired[list[str]]
    error: NotRequired[str | None]


class HermesRpgSuggestion(TypedDict, total=False):
    id: NotRequired[str]
    label: NotRequired[str]
    command: NotRequired[str]
    kind: NotRequired[str]
    risk: NotRequired[str]
    requires_user_click: NotRequired[bool]
    direct_state_write: NotRequired[bool]
    processed_by: NotRequired[str]
    reason: NotRequired[str]


class HermesRpgSuggestionsResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    read_only: NotRequired[bool]
    source: NotRequired[str]
    suggestions: NotRequired[list[HermesRpgSuggestion]]
    count: NotRequired[float]
    error: NotRequired[str | None]


class HermesApprovalResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    approved: NotRequired[bool]
    error: NotRequired[str | None]
    mode: NotRequired[str]
    request: NotRequired[dict[str, Any]]


class HermesRouteDecisionResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    source: NotRequired[str]
    mode: NotRequired[str]
    role: NotRequired[str]
    owner: NotRequired[str]
    review_required: NotRequired[bool]
    capabilities: NotRequired[list[str]]
    boundary: NotRequired[str]
    error: NotRequired[str | None]


class HermesCandidatePreview(TypedDict, total=False):
    name: NotRequired[str]
    target: NotRequired[str]
    before: NotRequired[dict[str, Any]]
    after: NotRequired[dict[str, Any]]
    risk: NotRequired[str]
    note: NotRequired[str]


class HermesCandidatePreviewResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    candidate: NotRequired[HermesCandidatePreview]
    preview_only: NotRequired[bool]


class HermesRecentResponse(TypedDict, total=False):
    ok: NotRequired[bool]
    items: NotRequired[list[dict[str, Any]]]
    count: NotRequired[float]
    source: NotRequired[str]


__all__ = [
    "HermesApprovalResponse",
    "HermesCandidatePreview",
    "HermesCandidatePreviewResponse",
    "HermesRecentResponse",
    "HermesRouteDecisionResponse",
    "HermesRpgApprovedFlowConfig",
    "HermesRpgApprovedFlowResponse",
    "HermesRpgExecutionLedgerItem",
    "HermesRpgExecutionLedgerResponse",
    "HermesRpgSequenceResponse",
    "HermesRpgSequenceStateResponse",
    "HermesRpgSuggestion",
    "HermesRpgSuggestionsResponse",
    "HermesRpgTurnReadoutResponse",
    "HermesRpgTurnReadoutResponseTurn",
    "HermesTestResponse",
    "HermesTestResponseResult",
    "HermesTestResponseResultResult",
]
