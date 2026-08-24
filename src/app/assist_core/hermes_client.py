from __future__ import annotations

import json
from typing import Any

import requests

from .core import AssistantRequest, AssistantResult
from .hermes_catalog import hermes_catalog_specs
from .hermes_contract import (
    hermes_contract_schema,
    hermes_request_from_assistant,
    hermes_request_payload,
    normalize_hermes_response,
    tool_calls_from_hermes,
)


_PROPOSAL_ONLY_SYSTEM_PROMPT = (
    "You are a non-executing JSON proposal formatter. Your entire final answer MUST be one JSON "
    "object beginning with { and ending with }. Do not use markdown fences, preambles, explanations, "
    "or follow-up questions. Never execute tools. Use exactly these top-level fields: state, response, "
    "domain, actions, requires_review, trace, error. Each action must use exactly these fields: tool, "
    "args, risk, reason. Actions may contain only allowlisted tools from the request; if no tool can "
    "satisfy the request, return an empty actions list and explain that in response. Set "
    "requires_review to true."
)


class HermesSidecarError(RuntimeError):
    pass


class HermesSidecarClient:
    """Small HTTP client for the Hermes sidecar API.

    Omnix asks Hermes for structured declarative plans and keeps execution,
    policy, budgets, and state ownership inside Omnix.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8642", api_key: str | None = None, timeout: float = 45.0):
        self.base_url = base_url.rstrip("/"); self.api_key = api_key; self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> dict[str, Any]:
        response=requests.get(f"{self.base_url}/health",headers=self._headers(),timeout=min(5.0,self.timeout));response.raise_for_status();return response.json()

    def capabilities(self) -> dict[str, Any]:
        response=requests.get(f"{self.base_url}/v1/capabilities",headers=self._headers(),timeout=min(5.0,self.timeout));response.raise_for_status();return response.json()

    def rpg_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        response=requests.post(f"{self.base_url}/v1/rpg/plan",headers=self._headers(),data=json.dumps(request),timeout=self.timeout);response.raise_for_status();data=response.json()
        if not isinstance(data,dict): raise HermesSidecarError("Hermes RPG planner response was not an object")
        return data

    def plan_research(self, request: Any) -> Any:
        from app.research.planner import ResearchPlan, ResearchPlanningRequest, research_planning_payload
        validated_request=ResearchPlanningRequest.model_validate(request)
        payload={"model":"hermes-agent","stream":False,"messages":[
            {"role":"system","content":"Return only valid JSON matching the supplied research schema. Do not execute operations and do not propose operations outside the allowlist."},
            {"role":"user","content":json.dumps(research_planning_payload(validated_request),sort_keys=True)}]}
        response=requests.post(f"{self.base_url}/v1/chat/completions",headers=self._headers(),data=json.dumps(payload),timeout=self.timeout);response.raise_for_status();content=self._extract_content(response.json())
        try:return ResearchPlan.model_validate(json.loads(_strip_json_fence(content)))
        except Exception as exc:raise HermesSidecarError("Hermes did not return a valid research plan") from exc

    def plan_trading_research_next(self, request: Any, context: Any) -> Any:
        """Return exactly one proposal-only semantic trading research action."""
        from app.trading.research.contracts import TradingResearchRequest
        from app.trading.research.hermes_contract import TradingHermesContext, TradingHermesNextActionDecision, trading_next_action_payload
        validated_request=TradingResearchRequest.model_validate(request); validated_context=TradingHermesContext.model_validate(context)
        payload={"model":"hermes-agent","stream":False,"response_format":{"type":"json_object"},"messages":[
            {"role":"system","content":("You are a non-executing trading research next-action planner. Return exactly one JSON action matching the supplied schema. "
                "Never execute anything. Never propose orders, position sizing, broker actions, strategy mutation, shell, files, GitHub, or unlisted operations. "
                "Use the evidence summary to decide the single highest-value unresolved follow-up, or stop.")},
            {"role":"user","content":json.dumps(trading_next_action_payload(validated_request,validated_context),sort_keys=True,default=str)}]}
        response=requests.post(f"{self.base_url}/v1/chat/completions",headers=self._headers(),data=json.dumps(payload),timeout=self.timeout);response.raise_for_status();content=self._extract_content(response.json())
        try:return TradingHermesNextActionDecision.model_validate(json.loads(_strip_json_fence(content)))
        except Exception as exc:raise HermesSidecarError("Hermes did not return a valid trading next-action proposal") from exc

    def plan(self, request: AssistantRequest) -> AssistantResult:
        prompt=self._planner_prompt(request);payload={"model":"hermes-agent","stream":False,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":_PROPOSAL_ONLY_SYSTEM_PROMPT},{"role":"user","content":prompt}]}
        response=requests.post(f"{self.base_url}/v1/chat/completions",headers=self._headers(),data=json.dumps(payload),timeout=self.timeout);response.raise_for_status();return self._parse_plan(self._extract_content(response.json()),request)

    def _planner_prompt(self, request: AssistantRequest) -> str:
        contract_request=hermes_request_from_assistant(request,available_tools=hermes_catalog_specs())
        return json.dumps({"task":"Create an Omnix execution plan. Do not execute tools.","schema":hermes_contract_schema(),"request":hermes_request_payload(contract_request)},sort_keys=True)

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:return data["choices"][0]["message"]["content"]
        except Exception as exc:raise HermesSidecarError("Hermes response did not include message content") from exc

    def _parse_plan(self, content: str, request: AssistantRequest) -> AssistantResult:
        try:plan=json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as exc:raise HermesSidecarError("Hermes did not return valid planner JSON") from exc
        normalized=normalize_hermes_response(plan,fallback_domain=request.domain)
        return AssistantResult(success=normalized.state!="rejected" and not normalized.error,response=normalized.response,domain=normalized.domain,
            tool_calls=tool_calls_from_hermes(normalized),requires_confirmation=normalized.requires_review,error=normalized.error)


def _strip_json_fence(content: str) -> str:
    text=str(content or "").strip()
    if text.startswith("```"):
        text=text.strip("`")
        if text.lower().startswith("json"):text=text[4:].strip()
    return text
