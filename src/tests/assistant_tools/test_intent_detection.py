from fastapi.testclient import TestClient

from app.assistant_tools.intent import detect_assistant_tool_intent
from app.gateway.main import create_gateway_app


def test_detect_assistant_tool_intent_for_email_draft():
    intent = detect_assistant_tool_intent("Draft an email to Ada")

    assert intent.detected is True
    assert intent.tool_id == "gmail"
    assert intent.action_id == "gmail.create_draft"


def test_detect_assistant_tool_intent_for_availability():
    intent = detect_assistant_tool_intent("Check my calendar availability tomorrow")

    assert intent.detected is True
    assert intent.tool_id == "calendar"
    assert intent.action_id == "calendar.read_availability"


def test_assistant_tool_intent_route_returns_preview():
    client = TestClient(create_gateway_app())

    response = client.post("/api/assistant/tools/intent", json={"message": "Find Ada in contacts"})

    assert response.status_code == 200
    assert response.json()["detected"] is True
    assert response.json()["tool_id"] == "contacts"
