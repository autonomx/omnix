from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.providers import ChatMessage
from app.providers.base import ChatResponse
from app.providers.structured import (
    ProviderEmptyResponse,
    ProviderTruncatedResponse,
    StructuredCapabilities,
    StructuredContract,
    StructuredMode,
    StructuredOutputError,
    StructuredOutputExhausted,
    StructuredOutputGateway,
    StructuredRetryBudget,
)
from app.runtime.http_client import shared_http_client

from .core import AssistantRequest, AssistantResult
from .hermes_catalog import hermes_catalog_specs
from .hermes_contract import (
    hermes_contract_schema,
    hermes_request_from_assistant,
    hermes_request_payload,
    normalize_hermes_response,
    tool_calls_from_hermes,
)
from app.prompts import prompt_template


PROPOSAL_ONLY_SYSTEM_PROMPT_TEMPLATE = prompt_template(
    'assist_core.hermes_client.proposal_only_system_prompt', "1",
    (
        'You are a non-executing JSON proposal formatter. Your entire final answer MUST be one '
        'JSON object beginning with { and ending with }. Do not use markdown fences, preambles, '
        'explanations, or follow-up questions. Never execute tools. Use exactly these top-level '
        'fields: state, response, domain, actions, requires_review, trace, error. Each action '
        'must use exactly these fields: tool, args, risk, reason. Actions may contain only '
        'allowlisted tools from the request; if no tool can satisfy the request, return an empty '
        'actions list and explain that in response. Set requires_review to true.'
    ),
)

PLANNER_PROMPT_TEMPLATE = prompt_template(
    'assist_core.hermes_client.planner_prompt', "1",
    'Create an Omnix execution plan. Do not execute tools.',
)



_PROPOSAL_ONLY_SYSTEM_PROMPT = (
    PROPOSAL_ONLY_SYSTEM_PROMPT_TEMPLATE.text
)


class HermesSidecarError(RuntimeError):
    pass


class _JsonObject(BaseModel):
    """One JSON object, checked further by the caller."""

    model_config = ConfigDict(extra="allow")


class _HermesChatProvider:
    """The sidecar's chat endpoint as a provider for the structured-output gateway.

    The request is the one the client sent before the gateway: model
    ``hermes-agent``, no temperature, and ``response_format`` JSON object only
    for the calls that asked for it.
    """

    provider_name = "hermes"
    config = None

    def __init__(self, client: "HermesSidecarClient", *, json_mode: bool, timeout: float) -> None:
        self._client = client
        self._json_mode = json_mode
        self._timeout = timeout

    def get_structured_capabilities(self, model: str | None = None) -> StructuredCapabilities:
        mode = StructuredMode.JSON_OBJECT if self._json_mode else StructuredMode.TEXT_JSON
        return StructuredCapabilities(preferred_modes=(mode,))

    def chat_completion(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": "hermes-agent",
            "stream": False,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        timeout = min(self._timeout, float(kwargs.get("request_timeout_seconds") or self._timeout))
        response = self._client.http.post(
            f"{self._client.base_url}/v1/chat/completions",
            headers=self._client._headers(),
            data=json.dumps(payload),
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = self._client._extract_content(data)
        choice = data["choices"][0] if isinstance(data.get("choices"), list) and data["choices"] else {}
        return ChatResponse(
            content=content if isinstance(content, str) else "",
            model=str(data.get("model") or "hermes-agent"),
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
            finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
        )


class HermesSidecarClient:
    """Small HTTP client for the Hermes sidecar API.

    Omnix asks Hermes for structured declarative plans and keeps execution,
    policy, budgets, and state ownership inside Omnix.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8642", api_key: str | None = None, timeout: float = 45.0):
        self.base_url = base_url.rstrip("/"); self.api_key = api_key; self.timeout = timeout
        self.http = shared_http_client("hermes")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> dict[str, Any]:
        response=self.http.get(f"{self.base_url}/health",headers=self._headers(),timeout=min(5.0,self.timeout));response.raise_for_status();return response.json()

    def capabilities(self) -> dict[str, Any]:
        response=self.http.get(f"{self.base_url}/v1/capabilities",headers=self._headers(),timeout=min(5.0,self.timeout));response.raise_for_status();return response.json()

    def rpg_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        response=self.http.post(f"{self.base_url}/v1/rpg/plan",headers=self._headers(),data=json.dumps(request),timeout=self.timeout);response.raise_for_status();data=response.json()
        if not isinstance(data,dict): raise HermesSidecarError("Hermes RPG planner response was not an object")
        return data

    def plan_research(self, request: Any) -> Any:
        from app.research.planner import ResearchPlan, ResearchPlanningRequest, research_planning_payload
        validated_request=ResearchPlanningRequest.model_validate(request)
        return self._structured(
            [ChatMessage(role="system", content="Return only valid JSON matching the supplied research schema. Do not execute operations and do not propose operations outside the allowlist."),
             ChatMessage(role="user", content=json.dumps(research_planning_payload(validated_request), sort_keys=True))],
            output_model=ResearchPlan, contract_id="hermes.research_plan", json_mode=False,
            timeout=self.timeout, error="Hermes did not return a valid research plan",
        )

    def plan_trading_research_next(self, request: Any, context: Any) -> Any:
        """Return exactly one proposal-only semantic trading research action."""
        from app.trading.research.contracts import TradingResearchRequest
        from app.trading.research.hermes_contract import TradingHermesContext, TradingHermesNextActionDecision, trading_next_action_payload
        validated_request=TradingResearchRequest.model_validate(request); validated_context=TradingHermesContext.model_validate(context)
        return self._structured(
            [ChatMessage(role="system", content=("You are a non-executing trading research next-action planner. Return exactly one JSON action matching the supplied schema. "
                "Never execute anything. Never propose orders, position sizing, broker actions, strategy mutation, shell, files, GitHub, or unlisted operations. "
                "Use the evidence summary to decide the single highest-value unresolved follow-up, or stop.")),
             ChatMessage(role="user", content=json.dumps(trading_next_action_payload(validated_request, validated_context), sort_keys=True, default=str))],
            output_model=TradingHermesNextActionDecision, contract_id="hermes.trading_next_action", json_mode=True,
            timeout=self.timeout, error="Hermes did not return a valid trading next-action proposal",
        )

    def classify_agent_evidence(self, task: str, profile_id: str) -> dict[str, Any]:
        """Proposal-only semantic evidence classification for ambiguous Agent tasks.

        This method never executes tools. Omnix validates the returned source
        classes against the selected profile ceiling before issuing authority.
        """
        schema = {
            "requirement": "none|optional|required",
            "external_access": "allowed|forbidden",
            "requirements": [
                {
                    "source_class": (
                        "general_current_web|breaking_news|market_news|company_filing|"
                        "software_release|repo_contents|repo_ci_state|home_state|"
                        "home_energy|calendar_state|email_state|market_quote|"
                        "market_status|weather_state"
                    ),
                    "freshness": "timeless|current",
                    "trust_floor": "authoritative|primary|reputable|general",
                    "fallback_policy": "fail_closed|allow_fallback",
                }
            ],
            "user_visible_attribution": "none|when_used|required",
            "retrieval_strategy": "lookup|bounded|adaptive",
            "confidence": "number 0..1",
            "reason": "short string",
        }
        decision = self._structured(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "You are a non-executing evidence-policy adviser. Return one JSON object "
                        "matching the supplied schema. Determine whether the task needs external "
                        "evidence, what semantic source classes are required, freshness/trust, and "
                        "attribution. Never execute tools, never name unlisted source classes, and "
                        "never grant capabilities."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        {"task": task, "profile": profile_id, "schema": schema},
                        sort_keys=True,
                    ),
                ),
            ],
            output_model=_JsonObject,
            contract_id="hermes.evidence_decision",
            json_mode=True,
            timeout=min(self.timeout, 15.0),
            error="Hermes did not return a valid evidence decision",
        )
        return decision.model_dump()

    def plan(self, request: AssistantRequest) -> AssistantResult:
        plan = self._structured(
            [ChatMessage(role="system", content=_PROPOSAL_ONLY_SYSTEM_PROMPT),
             ChatMessage(role="user", content=self._planner_prompt(request))],
            output_model=_JsonObject, contract_id="hermes.assistant_plan", json_mode=True,
            timeout=self.timeout, error="Hermes did not return valid planner JSON",
        )
        normalized=normalize_hermes_response(plan.model_dump(),fallback_domain=request.domain)
        return AssistantResult(success=normalized.state!="rejected" and not normalized.error,response=normalized.response,domain=normalized.domain,
            tool_calls=tool_calls_from_hermes(normalized),requires_confirmation=normalized.requires_review,error=normalized.error)

    def _structured(
        self,
        messages: list[ChatMessage],
        *,
        output_model: type[BaseModel],
        contract_id: str,
        json_mode: bool,
        timeout: float,
        error: str,
    ) -> Any:
        """One sidecar call for a JSON object validated against ``output_model``.

        Unusable output raises ``HermesSidecarError(error)``; a transport or HTTP
        failure is raised unchanged, as before the gateway.
        """
        contract = StructuredContract(
            contract_id=contract_id,
            version=1,
            output_model=output_model,
            regenerate_on_semantic_failure=False,
        )
        budget = StructuredRetryBudget(
            max_provider_calls=1,
            max_transport_retries=0,
            max_format_downgrades=0,
            max_validation_regenerations=0,
            deadline_seconds=timeout + 5.0,
        )
        provider = _HermesChatProvider(self, json_mode=json_mode, timeout=timeout)
        try:
            return StructuredOutputGateway(provider).generate(
                messages, contract=contract, retry_budget=budget,
                provider_options={"request_timeout_seconds": timeout},
            )
        except StructuredOutputExhausted as exc:
            cause = exc.last_error
            if cause is not None and not isinstance(cause, (ProviderEmptyResponse, ProviderTruncatedResponse)):
                raise cause from None
            raise HermesSidecarError(error) from exc
        except StructuredOutputError as exc:
            raise HermesSidecarError(error) from exc

    def _planner_prompt(self, request: AssistantRequest) -> str:
        contract_request=hermes_request_from_assistant(request,available_tools=hermes_catalog_specs())
        return json.dumps({"task":PLANNER_PROMPT_TEMPLATE.text,"schema":hermes_contract_schema(),"request":hermes_request_payload(contract_request)},sort_keys=True)

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:return data["choices"][0]["message"]["content"]
        except Exception as exc:raise HermesSidecarError("Hermes response did not include message content") from exc
