from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent_runtime.api import StartAgentRunRequest, router
from app.agent_runtime.profiles import AgentProfile, get_agent_profile
from app.agent_runtime.request_policy import allowed_workspace_root, validate_request_policy


def test_public_request_cannot_loosen_approval():
    with pytest.raises(ValidationError, match="only tighten"):
        StartAgentRunRequest(task="inspect", provider_id="test", model_id="test", approval_policy="allow_automatic")


@pytest.mark.parametrize("policy", ["ask_sensitive", "always_ask", "disabled"])
def test_public_request_can_tighten_approval(policy):
    request = StartAgentRunRequest(task="inspect", provider_id="test", model_id="test", approval_policy=policy)
    assert request.approval_policy == policy


def test_public_request_normalizes_windows_path_patterns():
    request = StartAgentRunRequest(task="inspect", provider_id="test", model_id="test", allowed_paths=["src\\components\\**"])
    assert request.allowed_paths == ["src/components/**"]


@pytest.mark.parametrize("path", ["../secrets", "src/../../secrets", "..\\secrets", "/etc/**", "C:\\secrets\\**", "C:secrets", "\\\\server\\share", "", "src/\x00secret"])
def test_allowed_paths_cannot_escape_workspace(path):
    with pytest.raises(ValueError, match="relative workspace"):
        validate_request_policy(get_agent_profile("coding"), approval_policy="ask_sensitive", isolation_policy="supervised_worktree", allowed_paths=[path])


@pytest.mark.parametrize("paths", [["src/**"], ["src/component.py"], ["src\\components\\**"]])
def test_paths_may_narrow_a_profile_ceiling(paths):
    profile = AgentProfile(id="test", description="test", allowed_paths=("src/**",))
    validate_request_policy(profile, approval_policy="always_ask", isolation_policy="supervised_worktree", allowed_paths=paths)


@pytest.mark.parametrize("paths", [["**"], ["src-other/**"], ["s*/**"], []])
def test_paths_cannot_widen_a_profile_ceiling(paths):
    profile = AgentProfile(id="test", description="test", allowed_paths=("src/**",))
    with pytest.raises(ValueError, match="allowed paths"):
        validate_request_policy(profile, approval_policy="ask_sensitive", isolation_policy="supervised_worktree", allowed_paths=paths)


def test_isolation_cannot_be_lowered():
    profile = AgentProfile(id="test", description="test", isolation_policy="docker_strong")
    with pytest.raises(ValueError, match="only raise"):
        validate_request_policy(profile, approval_policy="ask_sensitive", isolation_policy="supervised_worktree", allowed_paths=["**"])


@pytest.mark.parametrize("policy", ["docker_strong", "unattended"])
def test_isolation_can_be_raised(policy):
    validate_request_policy(get_agent_profile("coding"), approval_policy="ask_sensitive", isolation_policy=policy, allowed_paths=["**"])


def test_unknown_isolation_is_rejected_before_service_start():
    with pytest.raises(ValidationError, match="unknown isolation"):
        StartAgentRunRequest(task="inspect", provider_id="test", model_id="test", isolation_policy="none")


def test_only_reviewer_can_request_review_snapshot():
    with pytest.raises(ValidationError, match="reviewer profile"):
        StartAgentRunRequest(task="inspect", provider_id="test", model_id="test", isolation_policy="immutable_review_snapshot")


def test_workspace_roots_use_operator_allow_list(monkeypatch, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    monkeypatch.setenv("OMNIX_AGENT_WORKSPACE_ROOTS", os.pathsep.join([str(first), str(second)]))
    assert allowed_workspace_root(str(first / "project")) == str((first / "project").resolve())
    assert allowed_workspace_root(str(second)) == str(second.resolve())
    with pytest.raises(ValueError, match="outside"):
        allowed_workspace_root(str(tmp_path / "first-other"))
    with pytest.raises(ValueError, match="outside"):
        allowed_workspace_root(str(first / ".." / "outside"))


def test_empty_configured_roots_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_AGENT_WORKSPACE_ROOTS", "")
    with pytest.raises(ValueError, match="outside"):
        allowed_workspace_root(str(tmp_path))


def test_relative_workspace_is_rejected(monkeypatch):
    monkeypatch.delenv("OMNIX_AGENT_WORKSPACE_ROOTS", raising=False)
    with pytest.raises(ValueError, match="absolute"):
        allowed_workspace_root("resources/agent_workspaces/project")


def test_default_workspace_roots_are_repository_scoped(monkeypatch):
    monkeypatch.delenv("OMNIX_AGENT_WORKSPACE_ROOTS", raising=False)
    root = Path(__file__).resolve().parents[3]
    assert allowed_workspace_root(str(root)) == str(root)
    with pytest.raises(ValueError, match="outside"):
        allowed_workspace_root(str(root.parent / "outside"))


def test_http_policy_rejection_precedes_service_access(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_AGENT_WORKSPACE_ROOTS", str(tmp_path / "allowed"))
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        request = {"task": "inspect", "provider_id": "test", "model_id": "test", "repository": str(tmp_path / "allowed")}
        assert client.post("/api/agent-runs", json={**request, "approval_policy": "allow_automatic"}).status_code == 422
        response = client.post("/api/agent-runs", json={**request, "workspace_root": str(tmp_path / "outside")})
        assert response.status_code == 422
        assert "outside OMNIX_AGENT_WORKSPACE_ROOTS" in response.json()["detail"]
        response = client.post("/api/agent-runs", json={**request, "repository": str(tmp_path / "outside"), "workspace_root": str(tmp_path / "allowed")})
        assert response.status_code == 422
