from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime import chat_bridge
from app.agent_runtime.chat_bridge import (
    _agent_task,
    _direct_request,
    _select_profile,
    _unauthorized_agent_command,
    route_typed_chat_turn,
)
from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.router import route_omnix_request


def test_direct_home_request_compiles_without_hermes() -> None:
    request = _direct_request(
        "Turn off the Desk Plug",
        session_id="chat-1",
        message_id="msg-1",
        capability_id="home.set_state",
    )
    assert request is not None
    assert request.action_id == "home.set_state"
    assert request.input == {"target": "Desk Plug", "state": "off"}
    assert request.proposal_id == "direct:chat-1:msg-1"


def test_open_ended_agentic_text_is_not_explicit_authority() -> None:
    decision = route_omnix_request("implement the missing feature")
    assert decision.lane == "agent"
    assert decision.explicit is False


def test_chat_profile_selection_is_semantic_and_bounded() -> None:
    assert _select_profile("fix the repository tests") == "coding"
    assert _select_profile("fix the trading UI") == "coding"
    assert _select_profile("turn off the kitchen plug") == "house"
    assert _select_profile("check my calendar") == "personal-assistant"
    assert _select_profile("research this stock") == "trading-research"
    assert _select_profile("investigate this topic") == "research"


def test_coding_profile_selection_covers_live_chat_coding_prompts() -> None:
    assert _select_profile("implement a small improvement to the agent router") == "coding"
    assert _select_profile(
        "/agent In `src/app/agent_runtime/router.py`, add a short comment and run pytest"
    ) == "coding"
    assert _select_profile(
        "/agent Review router.py and chat_bridge.py for routing inconsistencies and run router tests"
    ) == "coding"
    assert _select_profile("Push the current branch to origin and open a pull request") == "coding"
    assert _select_profile("research NVDA stock and summarize today's catalysts") == "trading-research"


def test_agent_prefix_is_removed_before_building_task() -> None:
    assert _agent_task("/agent implement the router change") == "implement the router change"


def test_explicit_agent_start_failure_does_not_fall_back_to_chat(monkeypatch, tmp_path) -> None:
    class _FailingService:
        def start(self, _spec):
            raise RuntimeError("pi executable unavailable")

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _FailingService())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent implement a small improvement to the agent router",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert "failed to start" in result.content
    assert result.metadata["omnix_route"]["lane"] == "agent"
    assert result.metadata["agent_start"]["durable"] is False


def test_publication_request_is_rejected_before_start_without_github_authority(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            raise AssertionError("publication request must not start a local-only run")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent Push the current branch to origin and open a pull request",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "github_publication_capability_not_issued"
    assert started == []


def test_research_request_starts_without_workspace(monkeypatch) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent research the latest PostgreSQL maintenance release",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "research"
    assert len(started) == 1
    assert started[0].workspace is None
    assert started[0].external_capabilities == ["research.web_search"]


def test_trade_execution_request_is_rejected_before_start(monkeypatch) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            raise AssertionError("research profile must not start for trade execution")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent Buy 10 shares of NVDA",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "trading_execution_capability_not_issued"
    assert started == []


def test_read_only_runs_reject_workspace_and_trading_mutations() -> None:
    def snapshot(profile: str):
        return SimpleNamespace(
            run_id="run-1",
            status="running",
            revision=1,
            last_error=None,
            spec=AgentRunSpec(
                run_id="run-1",
                task="research",
                profile=profile,
                model=ModelRef(provider_id="test", model_id="model"),
                capabilities=[],
                external_capabilities=["research.web_search"],
            ),
        )

    workspace_rejection = _unauthorized_agent_command(
        snapshot("research"),
        "edit the repository based on those findings",
    )
    trading_rejection = _unauthorized_agent_command(snapshot("trading-research"), "Buy 10 shares.")

    assert workspace_rejection is not None
    assert workspace_rejection["reason"] == "workspace_mutation_capability_not_issued"
    assert trading_rejection is not None
    assert trading_rejection["reason"] == "trading_execution_capability_not_issued"


def test_read_only_run_rejects_publication_without_github_capability() -> None:
    snapshot = SimpleNamespace(
        run_id="run-1",
        status="running",
        revision=1,
        last_error=None,
        spec=AgentRunSpec(
            run_id="run-1",
            task="coding",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            capabilities=["workspace.command"],
            external_capabilities=[],
        ),
    )

    rejection = _unauthorized_agent_command(snapshot, "push the current branch and open a pull request")

    assert rejection is not None
    assert rejection["reason"] == "github_publication_capability_not_issued"


def test_live_voice_metadata_can_be_detected_without_session_state() -> None:
    from app.agent_runtime.chat_bridge import _is_live_voice
    message = SimpleNamespace(metadata={"speech_segment_id": "voice-segment:abc"})
    assert _is_live_voice(message) is True
