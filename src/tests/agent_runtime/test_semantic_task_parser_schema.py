from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.agent_runtime.semantic_task_parser import ProviderSemanticTaskParser
from app.providers.base import ChatResponse


class _CapturingCodexProvider:
    provider_name = "chatgpt_codex"

    def __init__(self) -> None:
        self.config = SimpleNamespace(
            model="gpt-5.6-sol",
            timeout=30,
            base_url="",
        )
        self.response_format: dict[str, Any] | None = None

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        del messages, stream
        self.response_format = kwargs.get("response_format")
        payload = {
            "intent": "Rename the Omnix Profile button to Personality.",
            "subjects": [
                {
                    "target": "workspace",
                    "reference": "Omnix Profile button",
                    "kind": None,
                }
            ],
            "operations": [
                {
                    "kind": "modify",
                    "target": "workspace",
                    "subject_reference": "Profile button label",
                }
            ],
            "data_dependencies": [],
            "autonomous": False,
            "multi_step": False,
            "objective_relation": "none",
            "request_completeness": "self_contained",
            "replay_target": "latest_authoritative",
            "ambiguity": "none",
            "candidate_interpretations": [],
            "confidence": 0.99,
            "reason_code": "workspace_ui_label_change",
        }
        return ChatResponse(
            content=json.dumps(payload),
            model=str(model or self.config.model),
            finish_reason="stop",
        )


def test_codex_semantic_parser_projects_optional_fields_as_required_nullable() -> None:
    provider = _CapturingCodexProvider()
    parser = ProviderSemanticTaskParser(provider)

    task = parser.parse_contextual(
        "In Omnix app, change Profile name in code to Personality.",
        current_environment={"active_workspace": "F:/LLM/omnix"},
    )

    assert task.operations[0].kind == "modify"
    assert task.operations[0].target == "workspace"

    assert provider.response_format is not None
    schema = provider.response_format["json_schema"]["schema"]
    subjects = schema["properties"]["subjects"]["items"]
    assert subjects["required"] == list(subjects["properties"].keys())
    assert "kind" in subjects["required"]
    assert any(
        branch.get("type") == "null"
        for branch in subjects["properties"]["kind"]["anyOf"]
    )

    operations = schema["properties"]["operations"]["items"]
    assert operations["required"] == list(operations["properties"].keys())
    assert "subject_reference" in operations["required"]
