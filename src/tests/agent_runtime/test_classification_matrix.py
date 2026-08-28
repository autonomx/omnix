from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.chat_bridge import (
    _continue_agent_run,
    _direct_request,
    _select_profile,
)
from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.router import OmnixRouteDecision, route_omnix_request
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest


@pytest.mark.parametrize(
    "prompt",
    [
        "How do I fix this bug?",
        "Explain how to fix failing tests",
        "Why did the agent fix that file?",
        'What does "refactor this module" mean?',
        "Teach me how to implement a REST API",
        "How would you investigate this problem?",
        "What tests would you run to diagnose this?",
        'What happens if I say "/agent fix this"?',
        "Don't fix anything, just explain the problem",
        "Don't research this, just answer from memory",
        "Do not turn off the light",
        "I don't want you to debug it",
        "No need to implement anything",
        'What does "turn off the light" mean?',
        'Explain the phrase "fix the tests"',
        'Why would someone say "/agent debug this"?',
        "If I asked you to fix the tests, what would happen?",
        "How would an agent debug this?",
        "Could an agent research this topic?",
    ],
)
def test_non_actional_context_stays_chat(prompt: str) -> None:
    assert route_omnix_request(prompt).lane == "chat"


@pytest.mark.parametrize(
    "prompt,expected_lane",
    [
        ("Can you fix the failing tests?", "agent"),
        ("Could you debug this issue for me?", "agent"),
        ("Would you investigate this failure?", "agent"),
        ("Can you turn off the desk light?", "direct"),
        ("Can you check my calendar for conflicts?", "agent"),
        ("Send an email to Bob", "agent"),
        ("turn the thermostat down to 19 degrees C", "agent"),
    ],
)
def test_action_requests_keep_execution_intent(prompt: str, expected_lane: str) -> None:
    assert route_omnix_request(prompt).lane == expected_lane


@pytest.mark.parametrize(
    "prompt",
    [
        "Research NVIDIA's competitive position",
        "Analyze the Vancouver housing market using multiple sources",
        "Investigate the major economic trends of the last 60 days",
        "Research GME's prospects for the next month using multiple sources",
    ],
)
def test_web_research_mode_keeps_research_in_chat(prompt: str) -> None:
    assert route_omnix_request(prompt, research_mode="deep").lane == "chat"
    assert route_omnix_request(prompt, research_mode="quick").lane == "chat"


@pytest.mark.parametrize(
    "prompt,expected_profile",
    [
        ("/agent check all the lights", "house"),
        ("/agent make sure the outlets are okay", "house"),
        ("/agent summarize my emails", "personal-assistant"),
        ("/agent look up Alice in my contacts", "personal-assistant"),
        ("/agent research NVDA", "trading-research"),
        ("/agent investigate GME", "trading-research"),
        ("/agent research semiconductor stocks", "trading-research"),
        ("/agent research today's top gainers", "trading-research"),
        ("/agent short TSLA", "trading-research"),
        ("/agent cover the short", "trading-research"),
        ("/agent place an order for NVDA", "trading-research"),
        ("/agent cancel my order", "trading-research"),
        ("/agent git push", "coding"),
        ("/agent analyze the history of TCP", "research"),
        ("/agent research OpenAI's latest API changes", "research"),
    ],
)
def test_profile_selection_handles_plural_and_domain_signals(
    prompt: str,
    expected_profile: str,
) -> None:
    assert _select_profile(prompt) == expected_profile


@pytest.mark.parametrize(
    "prompt,expected_lane,expected_profile",
    [
        ("/agnet fix tests", "agent", "coding"),
        ("reseach NVDA", "agent", "trading-research"),
        ("anlyze NVDA", "agent", "trading-research"),
        ("turn of the light", "direct", "house"),
        ("chek my calendar", "agent", "personal-assistant"),
        ("debugg the router", "agent", "coding"),
    ],
)
def test_common_typos_are_classified_safely(
    prompt: str,
    expected_lane: str,
    expected_profile: str,
) -> None:
    decision = route_omnix_request(prompt)
    assert decision.lane == expected_lane
    assert _select_profile(prompt) == expected_profile
    if prompt.startswith("/agnet"):
        assert decision.explicit is True


def test_turn_of_typo_compiles_to_off() -> None:
    request = _direct_request(
        "turn of the light",
        session_id="chat-1",
        message_id="message-1",
        capability_id="home.set_state",
    )
    assert request is not None
    assert request.input == {"target": "light", "state": "off"}


@pytest.mark.parametrize(
    "prompt",
    [
        "Turn off the desk light and tell me a joke",
        "Check my calendar and research NVDA",
        "Fix the trading UI and then research NVDA",
        "Check my email and turn off the bedroom light",
        "Run bedtime routine and then summarize my email",
        "Research NVDA and buy it if it looks good",
        "Run bedtime routine and fix the thermostat bug",
    ],
)
def test_mixed_intent_uses_agent_adviser_without_partial_direct_execution(prompt: str) -> None:
    decision = route_omnix_request(prompt)
    assert decision.lane == "agent"
    assert decision.hermes_recommended is True
    assert decision.reason == "mixed_intent_task"


def test_research_mode_is_preserved_on_user_message_metadata(tmp_path) -> None:
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Research"))
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="Research PostgreSQL", research_mode="quick"),
    )
    assert appended is not None
    _, message = appended
    assert message.metadata["research_mode"] == "quick"


def test_cancel_rejects_single_pending_approval_before_run_control() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="coding",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    snapshot = SimpleNamespace(
        run_id="run-1",
        status="waiting_for_approval",
        revision=1,
        last_error=None,
        spec=spec,
    )

    class Service:
        command_type = None

        def approvals(self, _run_id: str, *, state: str):
            assert state == "pending"
            return [SimpleNamespace(approval_id="approval-1")]

        def command(self, command):
            self.command_type = command.command_type
            return snapshot

    service = Service()
    result = _continue_agent_run(
        service,
        snapshot,
        "cancel",
        OmnixRouteDecision(lane="agent", confidence=1, reason="explicit_agent_mode"),
    )
    assert service.command_type == "reject"
    assert result.content.startswith("Rejection sent")
