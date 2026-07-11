from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .contracts import (
    AgencyEffect,
    CandidateSource,
    ResponseCandidate,
    ResponseMode,
    ResponseRequest,
    Reversibility,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
    coerce_response_mode,
)
from .renderer import ResponseRenderer


class CandidateAdapter(Protocol):
    def __call__(self, request: ResponseRequest) -> Sequence[ResponseCandidate]: ...


class RpgResponseGenerator:
    """Canonical owner of response candidate adaptation and visible rendering.

    Phase 1 intentionally keeps selection simple. Later phases replace the
    selection hook with hard eligibility, ranking, quality, and revalidation
    while preserving this entry point.
    """

    def __init__(
        self,
        *,
        candidate_adapter: CandidateAdapter | None = None,
        renderer: ResponseRenderer | None = None,
        selector: Callable[[Sequence[ResponseCandidate]], ResponseCandidate] | None = None,
    ) -> None:
        self._candidate_adapter = candidate_adapter or LegacyCandidateAdapter()
        self._renderer = renderer or ResponseRenderer()
        self._selector = selector or self._select_first_candidate

    def generate(self, request: ResponseRequest):
        candidates = tuple(self._candidate_adapter(request))
        if not candidates:
            candidates = (self._empty_candidate(request),)
        selected = self._selector(candidates)
        authoritative_deltas = _mapping(
            request.authoritative_turn_result.get("state_delta")
            or request.authoritative_turn_result.get("authoritative_deltas")
        )
        return self._renderer.render(
            selected.plan,
            authoritative_deltas=authoritative_deltas,
            metadata={
                "turn_id": request.turn_id,
                "candidate_id": selected.candidate_id,
                "candidate_source": selected.source.value,
                "runtime_mode": request.runtime_mode,
                "candidate_count": len(candidates),
            },
        )

    def shadow_compare(
        self,
        request: ResponseRequest,
        *,
        legacy_visible_text: str,
    ) -> dict[str, Any]:
        rendered = self.generate(request)
        return {
            "format_version": "rpg_response_shadow_v1",
            "turn_id": request.turn_id,
            "legacy_visible_text": legacy_visible_text,
            "canonical_visible_text": rendered.text,
            "changed": rendered.text.strip() != legacy_visible_text.strip(),
            "mode": rendered.mode.value,
            "approved_section_ids": list(rendered.approved_section_ids),
            "authoritative_state_unchanged": True,
        }

    @staticmethod
    def _select_first_candidate(candidates: Sequence[ResponseCandidate]) -> ResponseCandidate:
        return candidates[0]

    @staticmethod
    def _empty_candidate(request: ResponseRequest) -> ResponseCandidate:
        plan = SemanticResponsePlan(
            mode=ResponseMode.RECOVERY,
            sections=(
                SemanticSection(
                    section_id="empty.clarification",
                    section_type=SectionType.CLARIFICATION,
                    text="What would you like to accomplish here?",
                ),
            ),
            forward_strategy="ask_clarification",
            agency_effect=AgencyEffect.CLARIFICATION_ONLY,
            reversibility=Reversibility.FULLY_REVERSIBLE,
        )
        return ResponseCandidate(
            candidate_id=f"{request.turn_id}:empty",
            plan=plan,
            source=CandidateSource.DETERMINISTIC,
        )


class LegacyCandidateAdapter:
    """Convert existing runtime/world-scene payloads into semantic plans."""

    def __call__(self, request: ResponseRequest) -> Sequence[ResponseCandidate]:
        payload = _mapping(request.legacy_payload)
        source = str(payload.get("source") or "").casefold()
        candidate_source = (
            CandidateSource.LEGACY_WORLD_SCENE
            if "world" in source or "scene" in source
            else CandidateSource.LEGACY_RUNTIME
        )
        plan = semantic_plan_from_legacy_payload(
            payload,
            mode=_infer_mode(request, payload),
        )
        return (
            ResponseCandidate(
                candidate_id=f"{request.turn_id}:legacy",
                plan=plan,
                source=candidate_source,
                provider_metadata={"legacy_source": payload.get("source") or ""},
            ),
        )


def semantic_plan_from_legacy_payload(
    payload: Mapping[str, Any],
    *,
    mode: ResponseMode,
) -> SemanticResponsePlan:
    sections: list[SemanticSection] = []
    narration = _text(payload.get("narration"))
    action = _text(payload.get("action"))
    result = _text(payload.get("result_text") or payload.get("result"))
    npc = _mapping(payload.get("npc"))
    npc_line = _text(npc.get("line") or payload.get("npc_line"))
    speaker = _text(npc.get("speaker") or payload.get("speaker"))

    if narration:
        sections.append(
            SemanticSection(
                section_id="legacy.narration",
                section_type=SectionType.NARRATION,
                text=narration,
                metadata={"legacy_field": "narration"},
            )
        )
    if action:
        sections.append(
            SemanticSection(
                section_id="legacy.action",
                section_type=SectionType.ACTION,
                text=action,
                metadata={"legacy_field": "action"},
            )
        )
    if result and not isinstance(payload.get("result"), Mapping):
        sections.append(
            SemanticSection(
                section_id="legacy.result",
                section_type=SectionType.RESULT,
                text=result,
                metadata={"legacy_field": "result"},
            )
        )
    if npc_line:
        sections.append(
            SemanticSection(
                section_id="legacy.npc",
                section_type=SectionType.NPC_DIALOGUE,
                text=npc_line,
                speaker_id=speaker,
                metadata={"legacy_field": "npc"},
            )
        )

    forward_strategy = _text(payload.get("forward_strategy")) or "answer_directly"
    agency_effect = _coerce_agency(payload.get("agency_effect"))
    reversibility = _coerce_reversibility(payload.get("reversibility"))
    return SemanticResponsePlan(
        mode=mode,
        sections=tuple(sections),
        forward_strategy=forward_strategy,
        agency_effect=agency_effect,
        reversibility=reversibility,
        metadata={"legacy_source": payload.get("source") or ""},
    )


def build_runtime_shadow_report(
    *,
    turn_id: str,
    player_input: str,
    runtime_payload: Mapping[str, Any],
    authoritative_turn_result: Mapping[str, Any] | None = None,
    legacy_visible_text: str = "",
) -> dict[str, Any]:
    request = ResponseRequest(
        turn_id=turn_id,
        player_input=player_input,
        authoritative_turn_result=dict(authoritative_turn_result or {}),
        runtime_mode="runtime_shadow",
        legacy_payload=dict(runtime_payload),
    )
    return RpgResponseGenerator().shadow_compare(
        request,
        legacy_visible_text=legacy_visible_text,
    )


def build_world_scene_shadow_report(
    *,
    turn_id: str,
    player_input: str,
    world_scene_payload: Mapping[str, Any],
    authoritative_turn_result: Mapping[str, Any] | None = None,
    legacy_visible_text: str = "",
) -> dict[str, Any]:
    payload = dict(world_scene_payload)
    payload.setdefault("source", "legacy_world_scene")
    request = ResponseRequest(
        turn_id=turn_id,
        player_input=player_input,
        authoritative_turn_result=dict(authoritative_turn_result or {}),
        runtime_mode="world_scene_shadow",
        legacy_payload=payload,
    )
    return RpgResponseGenerator().shadow_compare(
        request,
        legacy_visible_text=legacy_visible_text,
    )


def _infer_mode(request: ResponseRequest, payload: Mapping[str, Any]) -> ResponseMode:
    requested = (
        payload.get("response_mode")
        or payload.get("mode")
        or request.authoritative_turn_result.get("response_mode")
        or request.authoritative_turn_result.get("semantic_family")
        or request.authoritative_turn_result.get("action_type")
    )
    return coerce_response_mode(requested, ResponseMode.ACTION)


def _coerce_agency(value: Any) -> AgencyEffect:
    try:
        return AgencyEffect(str(value or AgencyEffect.NONE.value))
    except ValueError:
        return AgencyEffect.NONE


def _coerce_reversibility(value: Any) -> Reversibility:
    try:
        return Reversibility(str(value or Reversibility.FULLY_REVERSIBLE.value))
    except ValueError:
        return Reversibility.FULLY_REVERSIBLE


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
