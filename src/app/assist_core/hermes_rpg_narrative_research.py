from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.rpg.narrative_engine import (
    HermesResearchPolicy,
    HermesResearchRequest,
    normalize_hermes_research,
    run_bounded_hermes_research,
)


ResearchCallable = Callable[[HermesResearchRequest, HermesResearchPolicy], Mapping[str, Any]]


class _CallableResearcher:
    def __init__(self, callback: ResearchCallable) -> None:
        self.callback = callback

    def research(
        self,
        request: HermesResearchRequest,
        policy: HermesResearchPolicy,
    ) -> Mapping[str, Any]:
        return self.callback(request, policy)


def _request(data: Mapping[str, Any]) -> HermesResearchRequest:
    entity_ids = data.get("entity_ids")
    return HermesResearchRequest(
        research_id=str(data.get("research_id") or "").strip(),
        campaign_id=str(data.get("campaign_id") or data.get("session_id") or "").strip(),
        query=str(data.get("query") or "").strip(),
        entity_ids=tuple(
            str(value).strip()
            for value in entity_ids
            if str(value).strip()
        )[:16]
        if isinstance(entity_ids, list | tuple)
        else (),
        purpose=str(data.get("purpose") or "narrative_grounding").strip(),
        metadata=dict(data.get("metadata") or {}),
    )


def _policy(data: Mapping[str, Any]) -> HermesResearchPolicy:
    raw = data.get("policy") if isinstance(data.get("policy"), Mapping) else {}
    return HermesResearchPolicy(
        max_sources=int(raw.get("max_sources") or 6),
        max_findings=int(raw.get("max_findings") or 12),
        max_total_chars=int(raw.get("max_total_chars") or 8_000),
        max_excerpt_chars=int(raw.get("max_excerpt_chars") or 800),
        max_query_chars=int(raw.get("max_query_chars") or 500),
    ).bounded()


def hermes_rpg_narrative_research_payload(
    payload: Mapping[str, Any] | None,
    *,
    researcher: ResearchCallable | None = None,
) -> dict[str, Any]:
    """Run bounded read-only research or normalize an internal Hermes result."""

    data = dict(payload or {})
    request = _request(data)
    policy = _policy(data)
    try:
        if researcher is not None:
            result = run_bounded_hermes_research(
                request,
                _CallableResearcher(researcher),
                policy=policy,
            )
        else:
            raw = data.get("research_result")
            if not isinstance(raw, Mapping):
                return {
                    "ok": False,
                    "error": "hermes_narrative_research_not_configured",
                    "source": "hermes_rpg_narrative_research",
                    "read_only": True,
                    "state_changed": False,
                    "policy": policy.__dict__,
                }
            result = normalize_hermes_research(request, raw, policy=policy)
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "error": "invalid_hermes_narrative_research_request",
            "detail": str(exc),
            "source": "hermes_rpg_narrative_research",
            "read_only": True,
            "state_changed": False,
        }

    return {
        "ok": True,
        "source": "hermes_rpg_narrative_research",
        "read_only": True,
        "state_changed": False,
        "campaign_bible_changed": False,
        "result": result.as_dict(),
        "evidence": [record.as_dict() for record in result.evidence()],
        "policy": policy.__dict__,
    }
