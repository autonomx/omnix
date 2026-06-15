"""Contract tests for shared prompt rendering."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_prompt_renderer_adds_replay_metadata() -> None:
    from app.prompts import PromptRenderRequest, PromptTemplate, PromptTemplateRenderer

    rendered = PromptTemplateRenderer().render(
        PromptRenderRequest(
            template=PromptTemplate(
                id="story.summary",
                version="v1",
                module="storyteller",
                text="Summarize {title} in {tone}.",
                variables=["title", "tone"],
                provider_payload_format="completion_text",
            ),
            variables={"title": "The Signal", "tone": "one sentence"},
        )
    )

    assert rendered.rendered_text == "Summarize The Signal in one sentence."
    assert rendered.replay_metadata["template_id"] == "story.summary"
    assert rendered.replay_metadata["template_version"] == "v1"
    assert rendered.rendering_metadata["variable_names"] == ["title", "tone"]


def test_prompt_renderer_rejects_missing_variables() -> None:
    from app.prompts import PromptRenderError, PromptTemplate, PromptTemplateRenderer

    template = PromptTemplate(id="chat.reply", version="v1", module="chatbot", text="Reply to {message}.")

    try:
        PromptTemplateRenderer().render_template(template, {})
    except PromptRenderError as exc:
        assert "message" in str(exc)
    else:
        raise AssertionError("PromptRenderError was not raised")


def test_gateway_prompt_render_endpoint() -> None:
    from app.gateway.main import create_gateway_app

    client = TestClient(create_gateway_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/prompts/render",
        json={
            "template": {
                "id": "image.prompt",
                "version": "v1",
                "module": "image",
                "text": "Paint {subject}.",
                "provider_payload_format": "image_prompt",
            },
            "variables": {"subject": "a lantern"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rendered_text"] == "Paint a lantern."
    assert payload["provider_payload_format"] == "image_prompt"


def test_gateway_prompt_render_endpoint_reports_missing_variables() -> None:
    from app.gateway.main import create_gateway_app

    client = TestClient(create_gateway_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/prompts/render",
        json={
            "template": {
                "id": "image.prompt",
                "version": "v1",
                "module": "image",
                "text": "Paint {subject}.",
            },
            "variables": {},
        },
    )

    assert response.status_code == 400
    assert "subject" in response.json()["detail"]
