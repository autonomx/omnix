"""Run-scoped signed tokens for the broker and model gateway (WP-4.6)."""
from __future__ import annotations

import secrets
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.security import run_tokens
from app.security.run_tokens import (
    RunTokenError,
    capabilities_digest,
    issue_run_token,
    token_from_authorization,
    verify_run_token,
)

CLAIMS = {"run_id": "run-1", "workspace_id": "workspace:local", "owner": "agent-worker:1", "caps_digest": "d" * 64}


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.delenv("OMNIX_RUN_TOKEN_KEY", raising=False)


def test_round_trip_binds_the_run() -> None:
    token = issue_run_token(**CLAIMS)
    claims = verify_run_token(token, run_id="run-1")
    assert (claims.run_id, claims.workspace_id, claims.owner) == ("run-1", "workspace:local", "agent-worker:1")
    with pytest.raises(RunTokenError, match="run_token_run_mismatch"):
        verify_run_token(token, run_id="run-2")


def test_forged_expired_and_malformed_tokens_are_refused() -> None:
    token = issue_run_token(**CLAIMS)
    payload, signature = token.split(".")
    tampered = run_tokens._encode(run_tokens._decode(payload).replace(b"run-1", b"run-9")) + "." + signature
    with pytest.raises(RunTokenError, match="run_token_invalid"):
        verify_run_token(tampered, run_id="run-9")
    with pytest.raises(RunTokenError, match="run_token_expired"):
        verify_run_token(issue_run_token(**CLAIMS, ttl_seconds=10, now=1_000), run_id="run-1", now=1_011)
    for bad in ("", "abc", "a.b", "..."):
        with pytest.raises(RunTokenError):
            verify_run_token(bad, run_id="run-1")


def test_processes_of_one_installation_share_the_key(monkeypatch) -> None:
    token = issue_run_token(**CLAIMS)
    # Another process with the same launcher-issued service token verifies it.
    monkeypatch.setattr(run_tokens, "_PROCESS_KEY", None)
    assert verify_run_token(token, run_id="run-1").run_id == "run-1"
    # A different installation does not.
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    with pytest.raises(RunTokenError, match="run_token_invalid"):
        verify_run_token(token, run_id="run-1")


def test_explicit_key_must_be_long(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_RUN_TOKEN_KEY", "short")
    with pytest.raises(RunTokenError):
        issue_run_token(**CLAIMS)


def test_authorization_header_parsing() -> None:
    assert token_from_authorization(["OmnixRun abc"]) == "abc"
    assert token_from_authorization(["Bearer abc"]) == "abc"
    assert token_from_authorization(["Basic abc"]) is None
    assert token_from_authorization(["OmnixRun a", "OmnixRun b"]) is None
    assert token_from_authorization([]) is None


def test_capability_digest_is_order_independent() -> None:
    assert capabilities_digest(["b", "a"], ["x"]) == capabilities_digest(["a", "b", "a"], ["x"])
    assert capabilities_digest(["a"], ["x"]) != capabilities_digest(["a"], ["y"])


def _request_with(claims) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "state": {"omnix_run_token": claims}})


@pytest.mark.parametrize(
    ("snapshot", "detail"),
    [
        (None, "run_token_revoked"),
        (SimpleNamespace(status="completed", worker_id="agent-worker:1", spec=None), "run_token_revoked"),
        (SimpleNamespace(status="running", worker_id="agent-worker:1",
                         spec=SimpleNamespace(capabilities=["workspace.edit"], external_capabilities=[])),
         "run_token_capabilities_changed"),
        (SimpleNamespace(status="running", worker_id="agent-worker:2",
                         spec=SimpleNamespace(capabilities=[], external_capabilities=[])),
         "run_token_owner_changed"),
    ],
)
def test_live_run_guard_refuses_stale_tokens(monkeypatch, snapshot, detail) -> None:
    from app.agent_runtime import run_token_guard, service

    claims = verify_run_token(
        issue_run_token(**{**CLAIMS, "caps_digest": capabilities_digest([], [])}), run_id="run-1"
    )
    monkeypatch.setattr(service, "default_agent_run_service", lambda: SimpleNamespace(get=lambda _run_id: snapshot))
    with pytest.raises(HTTPException) as refused:
        run_token_guard.require_live_run_token(_request_with(claims))
    assert refused.value.status_code == 401
    assert refused.value.detail == detail


def test_live_run_guard_accepts_the_current_owner(monkeypatch) -> None:
    from app.agent_runtime import run_token_guard, service

    claims = verify_run_token(
        issue_run_token(**{**CLAIMS, "caps_digest": capabilities_digest(["workspace.read"], [])}), run_id="run-1"
    )
    snapshot = SimpleNamespace(status="waiting_for_approval", worker_id="agent-worker:1",
                               spec=SimpleNamespace(capabilities=["workspace.read"], external_capabilities=[]))
    monkeypatch.setattr(service, "default_agent_run_service", lambda: SimpleNamespace(get=lambda _run_id: snapshot))
    assert run_token_guard.require_live_run_token(_request_with(claims)) == claims
    with pytest.raises(HTTPException):
        run_token_guard.require_live_run_token(_request_with(None))


def test_docker_receives_the_token_by_name_only(tmp_path, monkeypatch) -> None:
    from app.agent_runtime import isolation
    from app.agent_runtime.contracts import AgentRunSpec, ModelRef

    spec = AgentRunSpec(run_id="run-1", task="t", model=ModelRef(provider_id="p", model_id="m"))
    runner = isolation.DockerStrongIsolation.__new__(isolation.DockerStrongIsolation)
    runner.docker, runner.image, runner.network = "docker", "image", "none"
    runner.operator_network = "none"
    runner.limits = SimpleNamespace(memory="1g", cpus="1", pids=64, tmpfs_size="64m")
    monkeypatch.setattr(runner, "validate", lambda: None, raising=False)
    env = {"OMNIX_AGENT_RUN_TOKEN": "secret-token", "OMNIX_AGENT_RUN_ID": "run-1"}
    command = runner.build_command(spec, argv=["pi"], cwd=tmp_path, env=env)
    assert "secret-token" not in " ".join(command)
    assert "OMNIX_AGENT_RUN_TOKEN" in command


def test_credentials_are_never_forwarded_to_child_processes(tmp_path) -> None:
    from app.agent_runtime.contracts import AgentRunSpec, ModelRef
    from app.agent_runtime.pi_runtime_core import build_agent_environment
    from app.runtime.process_environment import bounded_process_environment

    parent = {"PATH": "/bin", "OMNIX_SERVICE_TOKEN": "s", "OMNIX_RUN_TOKEN_KEY": "k" * 40, "OMNIX_AGENT_RUN_TOKEN": "t"}
    spec = AgentRunSpec(
        run_id="run-1", task="t", model=ModelRef(provider_id="p", model_id="m"),
        execution={"allowed_environment_keys": ["OMNIX_SERVICE_TOKEN", "OMNIX_RUN_TOKEN_KEY"]},
    )
    env = build_agent_environment(spec, tmp_path, parent_environment=parent)
    assert not {"OMNIX_SERVICE_TOKEN", "OMNIX_RUN_TOKEN_KEY", "OMNIX_AGENT_RUN_TOKEN"} & set(env)
    bounded = bounded_process_environment(parent, ["PATH", "OMNIX_SERVICE_TOKEN"], overrides={"OMNIX_AGENT_RUN_TOKEN": "t"})
    assert bounded == {"PATH": "/bin"}
