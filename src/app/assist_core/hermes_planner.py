"""Assist mode's planner: one proposal-only Hermes call per assistant request."""
from __future__ import annotations

import json

from app.prompts import prompt_template
from app.providers import ChatMessage
from app.providers.hermes_client import HermesSidecarClient, JsonObject

from app.assist_core.core import AssistantRequest, AssistantResult
from app.assist_core.hermes_catalog import hermes_catalog_specs
from app.assist_core.hermes_contract import (
    hermes_contract_schema,
    hermes_request_from_assistant,
    hermes_request_payload,
    normalize_hermes_response,
    tool_calls_from_hermes,
)


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


class HermesAssistantPlanner:
    """Asks the Hermes sidecar for a proposal; Omnix decides what runs."""

    def __init__(self, base_url: str = "http://127.0.0.1:8642", api_key: str | None = None, timeout: float = 45.0):
        self.client = HermesSidecarClient(base_url=base_url, api_key=api_key, timeout=timeout)

    def plan(self, request: AssistantRequest) -> AssistantResult:
        plan = self.client.structured(
            [ChatMessage(role="system", content=PROPOSAL_ONLY_SYSTEM_PROMPT_TEMPLATE.text),
             ChatMessage(role="user", content=_planner_prompt(request))],
            output_model=JsonObject, contract_id="hermes.assistant_plan", json_mode=True,
            timeout=self.client.timeout, error="Hermes did not return valid planner JSON",
        )
        normalized = normalize_hermes_response(plan.model_dump(), fallback_domain=request.domain)
        return AssistantResult(
            success=normalized.state != "rejected" and not normalized.error,
            response=normalized.response,
            domain=normalized.domain,
            tool_calls=tool_calls_from_hermes(normalized),
            requires_confirmation=normalized.requires_review,
            error=normalized.error,
        )


def _planner_prompt(request: AssistantRequest) -> str:
    contract_request = hermes_request_from_assistant(request, available_tools=hermes_catalog_specs())
    return json.dumps(
        {
            "task": PLANNER_PROMPT_TEMPLATE.text,
            "schema": hermes_contract_schema(),
            "request": hermes_request_payload(contract_request),
        },
        sort_keys=True,
    )
