from __future__ import annotations

import json
from typing import Any

import requests

from .core import AssistantRequest, AssistantResult
from .hermes_contract import (
    hermes_contract_schema,
    hermes_request_from_assistant,
    hermes_request_payload,
    normalize_hermes_response,
    tool_calls_from_hermes,
)


class HermesSidecarError(RuntimeError):
    pass


class HermesSidecarClient:
    """Small HTTP client for the Hermes sidecar API.

    Omnix asks Hermes for a structured plan and keeps execution inside Omnix.
    This avoids handing house or RPG state mutation to an external runtime
    before Omnix policy, dry-run, and confirmation checks run.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8642", api_key: str | None = None, timeout: float = 45.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/health", headers=self._headers(), timeout=min(5.0, self.timeout))
        response.raise_for_status()
        return response.json()

    def capabilities(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/v1/capabilities", headers=self._headers(), timeout=min(5.0, self.timeout))
        response.raise_for_status()
        return response.json()

    def plan(self, request: AssistantRequest) -> AssistantResult:
        prompt = self._planner_prompt(request)
        payload = {
            "model": "hermes-agent",
            "stream": False,
            "messages": [
                {"role": "system", "content": "Return only valid JSON matching the requested schema."},
                {"role": "user", "content": prompt},
            ],
        }
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = self._extract_content(data)
        return self._parse_plan(content, request)

    def _planner_prompt(self, request: AssistantRequest) -> str:
        contract_request = hermes_request_from_assistant(request)
        return json.dumps(
            {
                "task": "Create an Omnix execution plan. Do not execute tools.",
                "schema": hermes_contract_schema(),
                "request": hermes_request_payload(contract_request),
            },
            sort_keys=True,
        )

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise HermesSidecarError("Hermes response did not include message content") from exc

    def _parse_plan(self, content: str, request: AssistantRequest) -> AssistantResult:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            plan = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HermesSidecarError("Hermes did not return valid planner JSON") from exc

        normalized = normalize_hermes_response(plan, fallback_domain=request.domain)
        return AssistantResult(
            success=normalized.state != "rejected" and not normalized.error,
            response=normalized.response,
            domain=normalized.domain,
            tool_calls=tool_calls_from_hermes(normalized),
            requires_confirmation=normalized.requires_review,
            error=normalized.error,
        )
