"""N117.1 runtime presentation/session diagnostics bridge.

This module is intentionally presentation-only.  It exposes the runtime
current-turn prompt contract, NPC response architecture, provider payload
status, and grounding/fallback diagnostics to API/UI callers without changing
simulation outcomes.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _compact(value: Any, *, max_depth: int = 5, max_list: int = 12, max_str: int = 2000) -> Any:
    """Return a JSON-safe, bounded diagnostic copy."""
    if max_depth <= 0:
        if isinstance(value, dict):
            return {"truncated": True, "type": "dict"}
        if isinstance(value, list):
            return [{"truncated": True, "type": "list", "count": len(value)}]
        text = _safe_str(value)
        return text[:max_str]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, nested in list(value.items())[:80]:
            out[_safe_str(key)[:120]] = _compact(
                nested,
                max_depth=max_depth - 1,
                max_list=max_list,
                max_str=max_str,
            )
        if len(value) > 80:
            out["_truncated_key_count"] = len(value) - 80
        return out
    if isinstance(value, list):
        out = [
            _compact(item, max_depth=max_depth - 1, max_list=max_list, max_str=max_str)
            for item in value[:max_list]
        ]
        if len(value) > max_list:
            out.append({"_truncated_item_count": len(value) - max_list})
        return out
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > max_str:
            return value[:max_str].rstrip() + "..."
        return value
    return _safe_str(value)[:max_str]


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        item = _safe_dict(value)
        if item:
            return item
    return {}


def _diagnostic_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _safe_str(value).strip().lower()
    return text in {"1", "true", "yes", "on", "enabled"}


def runtime_presentation_debug_enabled(settings: Dict[str, Any] | None = None) -> bool:
    """Return whether runtime presentation diagnostics should be exposed.

    The helper defaults to true for development/runtime inspectors when no
    setting is provided, while still allowing callers to disable it explicitly.
    """
    settings = _safe_dict(settings)
    if "runtime_presentation_debug_enabled" in settings:
        return _diagnostic_flag(settings.get("runtime_presentation_debug_enabled"))
    if "presentation_debug_enabled" in settings:
        return _diagnostic_flag(settings.get("presentation_debug_enabled"))
    if "console_debug_enabled" in settings:
        return _diagnostic_flag(settings.get("console_debug_enabled"))
    return True


def build_runtime_presentation_diagnostics(
    *,
    artifact: Dict[str, Any] | None = None,
    payload: Dict[str, Any] | None = None,
    narration_context: Dict[str, Any] | None = None,
    provider_status: Dict[str, Any] | None = None,
    fallback_source: str | None = None,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a bounded UI/API diagnostic payload for a runtime turn.

    The diagnostic is read-only. It never creates outcomes and never changes the
    authoritative simulation/turn contract.
    """
    if not runtime_presentation_debug_enabled(settings):
        return {}

    artifact = _safe_dict(artifact)
    payload = _safe_dict(payload or artifact.get("narration_json"))
    narration_context = _safe_dict(narration_context or artifact.get("narration_context"))
    turn_contract = _safe_dict(
        narration_context.get("turn_contract")
        or artifact.get("turn_contract")
        or payload.get("turn_contract")
    )
    prompt_contract = _first_dict(
        payload.get("current_turn_prompt_contract"),
        artifact.get("current_turn_prompt_contract"),
        narration_context.get("current_turn_prompt_contract"),
    )
    npc_architecture = _first_dict(
        payload.get("npc_response_architecture"),
        artifact.get("npc_response_architecture"),
        narration_context.get("npc_response_architecture"),
    )
    grounding_guardrails = _first_dict(
        payload.get("grounding_guardrails"),
        artifact.get("grounding_guardrails"),
        narration_context.get("grounding_guardrails"),
    )
    provider_status = _safe_dict(provider_status or payload.get("provider_payload_status") or artifact.get("provider_payload_status"))

    diagnostics = {
        "format_version": "runtime_presentation_diagnostics_v1",
        "presentation_debug_available": True,
        "turn_id": _safe_str(artifact.get("turn_id") or narration_context.get("turn_id") or turn_contract.get("turn_id")),
        "fallback_source": _safe_str(
            fallback_source
            or payload.get("fallback_source")
            or artifact.get("fallback_source")
            or provider_status.get("fallback_source")
        ),
        "provider_payload_status": _compact(provider_status),
        "current_turn_prompt_contract": _compact(prompt_contract),
        "npc_response_architecture": _compact(npc_architecture),
        "grounding_guardrails": _compact(grounding_guardrails),
        "unsupported_combat_claim_guard": _compact(
            _first_dict(
                payload.get("unsupported_combat_claim_guard"),
                artifact.get("unsupported_combat_claim_guard"),
                provider_status.get("unsupported_combat_claim_guard"),
            )
        ),
        "service_economy_veto": _compact(
            _first_dict(
                payload.get("service_economy_veto"),
                artifact.get("service_economy_veto"),
                turn_contract.get("service_economy_veto"),
                turn_contract.get("service_resolver_veto"),
            )
        ),
        "authoritative_contract_summary": _compact(
            {
                "turn_id": turn_contract.get("turn_id"),
                "action_type": _safe_dict(turn_contract.get("action")).get("type")
                or _safe_dict(turn_contract.get("semantic_action")).get("action_type"),
                "has_combat_result": bool(_safe_dict(turn_contract.get("combat_result"))),
                "has_service_result": bool(_safe_dict(turn_contract.get("service_result"))),
                "has_travel_result": bool(_safe_dict(turn_contract.get("travel_result"))),
            }
        ),
    }
    diagnostics["has_prompt_contract"] = bool(prompt_contract)
    diagnostics["has_npc_response_architecture"] = bool(npc_architecture)
    diagnostics["has_grounding_guardrails"] = bool(grounding_guardrails)
    return diagnostics


def attach_runtime_presentation_diagnostics(
    response: Dict[str, Any],
    *,
    artifact: Dict[str, Any] | None = None,
    payload: Dict[str, Any] | None = None,
    narration_context: Dict[str, Any] | None = None,
    provider_status: Dict[str, Any] | None = None,
    fallback_source: str | None = None,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Attach diagnostics to a runtime API/event response in-place."""
    response = _safe_dict(response)
    diagnostics = build_runtime_presentation_diagnostics(
        artifact=artifact,
        payload=payload,
        narration_context=narration_context,
        provider_status=provider_status,
        fallback_source=fallback_source,
        settings=settings,
    )
    if diagnostics:
        response["runtime_presentation_diagnostics"] = diagnostics
        response["presentation_debug"] = diagnostics
    return response


def runtime_presentation_diagnostics_for_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract diagnostics from an SSE/API event without mutating it."""
    event = _safe_dict(event)
    diagnostics = _safe_dict(event.get("runtime_presentation_diagnostics") or event.get("presentation_debug"))
    if diagnostics:
        return copy.deepcopy(diagnostics)
    artifact = _safe_dict(event.get("artifact"))
    payload = _safe_dict(event.get("payload") or event.get("narration_json"))
    if artifact or payload:
        return build_runtime_presentation_diagnostics(artifact=artifact, payload=payload)
    return {}
