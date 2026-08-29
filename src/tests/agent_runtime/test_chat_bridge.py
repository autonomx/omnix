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
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
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


def test_quick_search_informational_turn_bypasses_agent_planner() -> None:
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="hows the weather in Vancouver right now?",
        metadata={"agent_mode": True, "research_mode": "quick"},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        context_items=[{"source_id": "web_search", "content": "Current weather"}],
    )

    assert result is None


def test_explicit_agent_request_still_uses_agent_lane_with_quick_search(monkeypatch) -> None:
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
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent research Vancouver weather sources",
        metadata={"agent_mode": True, "research_mode": "quick"},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        context_items=[{"source_id": "web_search", "content": "Current weather"}],
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "research"
    assert len(started) == 1


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


def test_read_only_runs_defer_workspace_mutation_to_revision_compiler_and_reject_trading_mutation() -> None:
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

    assert workspace_rejection is None
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



def test_attached_local_folder_overrides_default_coding_workspace(monkeypatch, tmp_path) -> None:
    selected = tmp_path / "selected"
    default = tmp_path / "default"
    selected.mkdir()
    default.mkdir()
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

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(default))
    session = SimpleNamespace(
        id="chat-workspace",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-workspace",
        content="/agent inspect the repository tests",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=None,
    )

    assert result is not None
    assert len(started) == 1
    workspace = started[0].workspace
    assert workspace is not None
    assert workspace.root == str(selected.resolve())
    assert workspace.repository is None
    assert workspace.worktree is None


def test_attached_local_folder_does_not_grant_workspace_to_research_profile(
    monkeypatch,
    tmp_path,
) -> None:
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

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-research-workspace",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-research-workspace",
        content="/agent research the latest PostgreSQL maintenance release",
        metadata={"workspace_root": str(tmp_path / "does-not-need-to-exist")},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=None,
    )

    assert result is not None
    assert len(started) == 1
    assert started[0].profile == "research"
    assert started[0].workspace is None


def test_invalid_attached_local_folder_fails_coding_run_before_start(
    monkeypatch,
    tmp_path,
) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            raise AssertionError("invalid workspace must not reach runtime start")

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-invalid-workspace",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-invalid-workspace",
        content="/agent inspect the repository tests",
        metadata={"workspace_root": str(tmp_path / "missing")},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=None,
    )

    assert result is not None
    assert started == []
    assert result.metadata["agent_start"]["status"] == "failed"
    assert "does not exist" in result.metadata["agent_start"]["error"]



def test_active_agent_rejects_switch_to_different_attached_workspace(
    monkeypatch,
    tmp_path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    snapshot = SimpleNamespace(
        run_id="active-workspace-run",
        status="running",
        revision=1,
        last_error=None,
        spec=AgentRunSpec(
            run_id="active-workspace-run",
            session_id="chat-active-workspace",
            task="inspect tests",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            capabilities=["workspace.read"],
            workspace=WorkspaceSpec(root=str(first)),
        ),
    )

    class _Service:
        def get(self, run_id):
            return snapshot if run_id == snapshot.run_id else None

        def command(self, _command):
            raise AssertionError("workspace-mismatched steering must not reach the active run")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(
        id="chat-active-workspace",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                role="assistant",
                metadata={"agent_run": {"run_id": snapshot.run_id}},
            )
        ],
    )
    message = SimpleNamespace(
        id="message-switch-workspace",
        content="/agent inspect the repository tests",
        metadata={"workspace_root": str(second)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=None,
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "active_run_workspace_mismatch"
    assert "different Local folder" in result.content
