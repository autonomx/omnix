"""Opt-in end-to-end coverage for the browser chat -> Semantic v2 -> PI path.

This test deliberately talks to a running Omnix gateway instead of replacing
the provider with a fixture.  It uses the same session and assistant-context
stream endpoints used by the web client after the context controller rewrites
the browser request.  The default provider/model are therefore selected by
the gateway, just as they are in the UI.

Run locally (with the gateway, default LLM, and ``pi`` available) with::

    $env:OMNIX_RUN_DEFAULT_LLM_AGENT_UI_TEST="1"
    python -m pytest src/tests/e2e/test_default_llm_agent_ui_flow.py -q --tb=short

The test is opt-in because it consumes a real model request and lets PI edit a
temporary git worktree.  Its polling budget is a test wait budget; it is not a
semantic parser timeout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any
from urllib.parse import quote

import httpx
import pytest


_TRUE = {"1", "true", "yes", "on"}
_PROMPT = (
    "in the attached workspace, change the system-mode settings button label "
    "from personality to profile in "
    "src/apps/web/src/features/chatbot/ChatIdentityModeControl.tsx"
)
_REVISED_PROMPT = (
    "now, in the attached workspace, change that system-mode settings button "
    "label from profile to personality in "
    "src/apps/web/src/features/chatbot/ChatIdentityModeControl.tsx"
)
_LATEST_PROMPT = (
    "now, in the attached workspace, change that system-mode settings button "
    "label from personality to profile in "
    "src/apps/web/src/features/chatbot/ChatIdentityModeControl.tsx"
)
_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
_RUN_ID_PATTERN = re.compile(r"\bAgent run ([A-Za-z0-9_-]+)")
_TARGET_FILES = (
    Path("src/apps/web/src/features/chatbot/ChatIdentityModeControl.tsx"),
)


def _seed_ui_label_edit_fixture(worktree: Path) -> None:
    target = worktree / _TARGET_FILES[0]
    text = target.read_text(encoding="utf-8")
    profile = "mode === 'character' ? 'Character settings' : 'Profile'"
    personality = "mode === 'character' ? 'Character settings' : 'Personality'"
    if text.count(personality) == 1 and profile not in text:
        return
    assert text.count(profile) == 1, target
    target.write_text(
        text.replace(profile, personality, 1),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(worktree), "add", str(_TARGET_FILES[0])],
        check=True,
        capture_output=True,
        timeout=30,
    )
    committed = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "-c",
            "user.name=Omnix live test",
            "-c",
            "user.email=omnix-live-test@example.invalid",
            "commit",
            "-m",
            "pre-edit UI label fixture",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert committed.returncode == 0, committed.stderr


def _enabled() -> bool:
    return str(os.environ.get("OMNIX_RUN_DEFAULT_LLM_AGENT_UI_TEST", "")).strip().casefold() in _TRUE


def _float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name, default) or default).strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return default


def _gateway_url() -> str:
    return (
        str(
            os.environ.get("OMNIX_GATEWAY_URL")
            or os.environ.get("OMNIX_API_BASE_URL")
            or "http://127.0.0.1:8000"
        )
        .strip()
        .rstrip("/")
    )


def _require_ok(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    pytest.fail(
        f"{operation} failed with HTTP {response.status_code}: "
        f"{response.text[:2000]}"
    )


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.split("\n\n"):
        data_lines = [line[6:] for line in block.splitlines() if line.startswith("data: ")]
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            pytest.fail(f"assistant stream returned invalid SSE JSON: {exc}: {block[:500]}")
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _create_isolated_repository(repository: Path) -> tuple[Path, Path]:
    # The gateway may run in a different Windows sandbox identity.  Keep the
    # temporary checkout under the shared repository volume so that its
    # Local-folder validator and PI process see the same path.
    shared_temp = repository / ".tmp"
    shared_temp.mkdir(exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="omnix-agent-ui-test-", dir=shared_temp))
    worktree = temp_root / "omnix"
    worktree.mkdir()
    try:
        tracked = subprocess.run(
            ["git", "-C", str(repository), "ls-files", "-z"],
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        for raw_path in tracked:
            if not raw_path:
                continue
            relative = Path(os.fsdecode(raw_path))
            source = repository / relative
            destination = worktree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination, follow_symlinks=False)
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "init",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        pytest.fail(f"could not create isolated repository: {exc}")
    if completed.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        pytest.fail(
            "could not initialize isolated repository: "
            f"{(completed.stderr or completed.stdout).strip()[:2000]}"
        )
    staged = subprocess.run(
        ["git", "-C", str(worktree), "add", "--all"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if staged.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        pytest.fail(f"could not stage isolated repository: {staged.stderr[:2000]}")
    committed = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "-c",
            "user.name=Omnix live test",
            "-c",
            "user.email=omnix-live-test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if committed.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        pytest.fail(f"could not commit isolated repository baseline: {committed.stderr[:2000]}")
    # Files created by the Codex sandbox inherit a private ACL.  The gateway
    # normally runs as the desktop user, so grant the local machine's
    # authenticated users access to this test-only checkout before advertising
    # it as the selected Local folder.
    shared_acl = subprocess.run(
        ["icacls", str(temp_root), "/grant", "*S-1-5-11:(OI)(CI)M", "/T"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if shared_acl.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        pytest.fail(f"could not share isolated repository with gateway: {shared_acl.stderr[:2000]}")
    return temp_root, worktree


def _remove_isolated_repository(temp_root: Path) -> None:
    shutil.rmtree(temp_root, ignore_errors=True)


def _approve_pending_runs(client: httpx.Client, run_id: str) -> None:
    approvals_response = client.get(f"/api/agent-runs/{quote(run_id, safe='')}/approvals")
    _require_ok(approvals_response, "list Agent approvals")
    approvals = approvals_response.json()
    if not isinstance(approvals, list):
        return
    for approval in approvals:
        if not isinstance(approval, dict) or approval.get("state") != "pending":
            continue
        approval_id = str(approval.get("approval_id") or "").strip()
        if not approval_id:
            continue
        command = client.post(
            f"/api/agent-runs/{quote(run_id, safe='')}/commands",
            json={
                "command_type": "approve",
                "payload": {"approval_id": approval_id},
                "idempotency_key": f"default-llm-agent-ui-test:{approval_id}",
            },
        )
        _require_ok(command, f"approve Agent capability {approval_id}")


def _wait_for_run(client: httpx.Client, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/agent-runs/{quote(run_id, safe='')}")
        _require_ok(response, "poll Agent run")
        latest = response.json()
        # Approval requests can be persisted while the worker remains in
        # ``running`` (PI may have emitted a progress message first).  Poll
        # them on every iteration so the UI's ask-sensitive policy does not
        # strand a validation command behind a race in status propagation.
        _approve_pending_runs(client, run_id)
        status = str(latest.get("status") or "")
        if status in _TERMINAL_RUN_STATUSES:
            return latest
        time.sleep(1.0)
    pytest.fail(
        f"Agent run {run_id} did not reach a terminal state within "
        f"{timeout_seconds:g}s: {json.dumps(latest, sort_keys=True)[:4000]}"
    )


@pytest.mark.e2e
def test_default_llm_ui_options_start_pi_and_update_profile_label() -> None:
    """The UI request options must hand the exact prompt to a PI coding run."""

    if not _enabled():
        pytest.skip(
            "default-LLM Agent UI flow is opt-in; set "
            "OMNIX_RUN_DEFAULT_LLM_AGENT_UI_TEST=1"
        )

    repository = Path(__file__).resolve().parents[3]
    temp_root, worktree = _create_isolated_repository(repository)
    _seed_ui_label_edit_fixture(worktree)
    run_id: str | None = None
    request_timeout = _float_env("OMNIX_DEFAULT_LLM_AGENT_UI_HTTP_TIMEOUT_SECONDS", 300.0)
    run_timeout = _float_env("OMNIX_DEFAULT_LLM_AGENT_UI_RUN_TIMEOUT_SECONDS", 900.0)

    try:
        timeout = httpx.Timeout(request_timeout, connect=min(15.0, request_timeout))
        with httpx.Client(base_url=_gateway_url(), timeout=timeout) as client:
            health = client.get("/health")
            _require_ok(health, "gateway health check")

            # These are the same provider/settings bootstrap calls made by the
            # web workspace.  The actual request intentionally omits provider_id
            # and model_id so the server's configured default route is selected.
            settings = client.get("/api/settings")
            _require_ok(settings, "load gateway settings")
            providers = client.get("/api/providers")
            _require_ok(providers, "load chat providers")

            created = client.post(
                "/api/chat/sessions",
                json={
                    "title": _PROMPT[:48],
                    "interaction_mode": "system",
                },
            )
            _require_ok(created, "create chat session")
            session = created.json()
            session_id = str(session.get("id") or "").strip()
            assert session_id, f"chat session response has no id: {session}"
            assert session.get("provider_id"), "session did not resolve the default provider"

            # The context controller sends these fields after the screenshot's
            # selections: No web research and Local folder · omnix.  Keep the
            # provider/model fields absent to exercise the app default LLM.
            payload = {
                "content": _PROMPT,
                "web_research_mode": "disabled",
                "workspace_root": str(worktree),
                "agent_mode": False,
                "dry_run": False,
                "coding_approval_policy": "ask_sensitive",
            }
            streamed = client.post(
                f"/api/assistant/context/chat/sessions/{quote(session_id, safe='')}/messages/stream",
                json=payload,
            )
            _require_ok(streamed, "send UI chat request through assistant context")
            events = _parse_sse(streamed.text)
            errors = [event for event in events if event.get("type") == "error"]
            assert not errors, f"assistant context stream returned errors: {errors}"

            complete = next(
                (event for event in events if event.get("type") == "complete"),
                None,
            )
            assert complete is not None, f"assistant stream had no completion event: {events}"
            content = str(complete.get("content") or "")
            metadata = complete.get("metadata")
            assert isinstance(metadata, dict), complete
            assert "Started coding Agent run" in content, content

            route = metadata.get("omnix_route")
            routing = metadata.get("routing_decision")
            compilation = metadata.get("semantic_compilation")
            assert isinstance(route, dict) and route.get("lane") == "agent", metadata
            assert isinstance(routing, dict), metadata
            assert routing.get("production_router") == "semantic_v2", routing
            assert routing.get("production_lane") == "agent", routing
            assert "legacy" not in routing, routing
            assert isinstance(compilation, dict) and compilation.get("profile_id") == "coding", metadata
            assert "workspace_mutate" in set(compilation.get("action_intents") or []), compilation

            agent_run = metadata.get("agent_run")
            if isinstance(agent_run, dict):
                run_id = str(agent_run.get("run_id") or "").strip() or None
            if not run_id:
                match = _RUN_ID_PATTERN.search(content)
                run_id = match.group(1) if match else None
            assert run_id, f"Agent start response did not expose a run id: {metadata}"

            snapshot = _wait_for_run(client, run_id, run_timeout)
            if snapshot.get("status") != "completed":
                diagnostic_events: Any = []
                diagnostic_response = client.get(
                    f"/api/agent-runs/{quote(run_id, safe='')}/events"
                )
                if diagnostic_response.is_success:
                    diagnostic_events = [
                        {
                            "event_type": event.get("event_type"),
                            "payload": event.get("payload"),
                        }
                        for event in diagnostic_response.json()
                        if event.get("event_type")
                        in {"tool.started", "tool.completed", "acceptance.completed"}
                    ]
                pytest.fail(
                    "PI Agent run did not complete: "
                    f"{json.dumps({'snapshot': snapshot, 'events': diagnostic_events}, sort_keys=True)[:12000]}"
                )
            spec = snapshot.get("spec")
            assert isinstance(spec, dict), snapshot
            assert spec.get("runtime") == "pi", spec
            assert spec.get("profile") == "coding", spec
            assert spec.get("task") == _PROMPT, spec
            assert spec.get("objective") == _PROMPT, spec
            assert spec.get("model", {}).get("provider_id"), spec
            assert spec.get("model", {}).get("model_id"), spec
            workspace = spec.get("workspace")
            assert isinstance(workspace, dict), spec
            assert Path(str(workspace.get("worktree") or workspace.get("root"))).resolve() == worktree.resolve(), spec

            run_events_response = client.get(
                f"/api/agent-runs/{quote(run_id, safe='')}/events"
            )
            _require_ok(run_events_response, "list PI Agent events")
            run_events = run_events_response.json()
            assert any(
                event.get("event_type") == "run.started"
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("source") == "pi"
                for event in run_events
            ), run_events
            assert any(
                event.get("event_type") == "tool.started"
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("source") == "pi"
                for event in run_events
            ), run_events

            identity_text = (worktree / _TARGET_FILES[0]).read_text(encoding="utf-8")
            assert "mode === 'character' ? 'Character settings' : 'Profile'" in identity_text
            changed_paths = {
                Path(path)
                for path in subprocess.run(
                    ["git", "-C", str(worktree), "diff", "--name-only"],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                ).stdout.splitlines()
            }
            assert set(_TARGET_FILES) <= changed_paths, changed_paths

            # Commit the first run's result so the second run starts from a
            # clean provenance baseline. The same UI chat then reverses the
            # requested rename; this guards against carrying the first
            # objective or its direction into a semantic ``revise`` turn.
            subprocess.run(
                ["git", "-C", str(worktree), "add", str(_TARGET_FILES[0])],
                check=True,
                capture_output=True,
                timeout=30,
            )
            revised_baseline = subprocess.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "-c",
                    "user.name=Omnix live test",
                    "-c",
                    "user.email=omnix-live-test@example.invalid",
                    "commit",
                    "-m",
                    "accept first Agent label update",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            assert revised_baseline.returncode == 0, revised_baseline.stderr

            revised_payload = {
                **payload,
                "content": _REVISED_PROMPT,
            }
            revised_stream = client.post(
                f"/api/assistant/context/chat/sessions/{quote(session_id, safe='')}/messages/stream",
                json=revised_payload,
            )
            _require_ok(revised_stream, "send revised UI chat request")
            revised_events = _parse_sse(revised_stream.text)
            revised_errors = [
                event for event in revised_events if event.get("type") == "error"
            ]
            assert not revised_errors, revised_errors
            revised_complete = next(
                (event for event in revised_events if event.get("type") == "complete"),
                None,
            )
            assert revised_complete is not None, revised_events
            revised_content = str(revised_complete.get("content") or "")
            revised_metadata = revised_complete.get("metadata")
            assert isinstance(revised_metadata, dict), revised_complete
            assert "Started coding Agent run" in revised_content, revised_content
            revised_routing = revised_metadata.get("routing_decision")
            assert isinstance(revised_routing, dict), revised_metadata
            assert revised_routing.get("production_router") == "semantic_v2"
            assert revised_routing.get("production_lane") == "agent"

            revised_agent_run = revised_metadata.get("agent_run")
            revised_run_id = (
                str(revised_agent_run.get("run_id") or "").strip()
                if isinstance(revised_agent_run, dict)
                else ""
            )
            if not revised_run_id:
                revised_match = _RUN_ID_PATTERN.search(revised_content)
                revised_run_id = revised_match.group(1) if revised_match else ""
            assert revised_run_id, revised_metadata
            run_id = revised_run_id

            revised_snapshot = _wait_for_run(client, revised_run_id, run_timeout)
            assert revised_snapshot.get("status") == "completed", revised_snapshot
            revised_spec = revised_snapshot.get("spec")
            assert isinstance(revised_spec, dict), revised_snapshot
            assert revised_spec.get("runtime") == "pi", revised_spec
            assert revised_spec.get("profile") == "coding", revised_spec
            assert revised_spec.get("task") == _REVISED_PROMPT, revised_spec
            assert revised_spec.get("objective") == _REVISED_PROMPT, revised_spec
            assert "Latest user revision" not in str(revised_spec.get("task") or "")
            assert _PROMPT not in str(revised_spec.get("task") or "")

            revised_run_events_response = client.get(
                f"/api/agent-runs/{quote(revised_run_id, safe='')}/events"
            )
            _require_ok(revised_run_events_response, "list revised PI Agent events")
            revised_run_events = revised_run_events_response.json()
            assert any(
                event.get("event_type") == "tool.started"
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("source") == "pi"
                for event in revised_run_events
            ), revised_run_events

            revised_identity_text = (worktree / _TARGET_FILES[0]).read_text(
                encoding="utf-8"
            )
            assert (
                "mode === 'character' ? 'Character settings' : 'Personality'"
                in revised_identity_text
            )
            assert (
                "mode === 'character' ? 'Character settings' : 'Profile'"
                not in revised_identity_text
            )

            # A third complete command returns to the original direction. The
            # default semantic model may call this a resume because it targets
            # the same component; that relation is telemetry and must not be
            # allowed to replace this latest self-contained command with the
            # preceding objective.
            subprocess.run(
                ["git", "-C", str(worktree), "add", str(_TARGET_FILES[0])],
                check=True,
                capture_output=True,
                timeout=30,
            )
            latest_baseline = subprocess.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "-c",
                    "user.name=Omnix live test",
                    "-c",
                    "user.email=omnix-live-test@example.invalid",
                    "commit",
                    "-m",
                    "accept revised Agent label update",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            assert latest_baseline.returncode == 0, latest_baseline.stderr

            latest_stream = client.post(
                f"/api/assistant/context/chat/sessions/{quote(session_id, safe='')}/messages/stream",
                json={**payload, "content": _LATEST_PROMPT},
            )
            _require_ok(latest_stream, "send latest UI chat request")
            latest_events = _parse_sse(latest_stream.text)
            latest_errors = [
                event for event in latest_events if event.get("type") == "error"
            ]
            assert not latest_errors, latest_errors
            latest_complete = next(
                (event for event in latest_events if event.get("type") == "complete"),
                None,
            )
            assert latest_complete is not None, latest_events
            latest_content = str(latest_complete.get("content") or "")
            latest_metadata = latest_complete.get("metadata")
            assert isinstance(latest_metadata, dict), latest_complete
            assert "Started coding Agent run" in latest_content, latest_content
            latest_agent_run = latest_metadata.get("agent_run")
            latest_run_id = (
                str(latest_agent_run.get("run_id") or "").strip()
                if isinstance(latest_agent_run, dict)
                else ""
            )
            if not latest_run_id:
                latest_match = _RUN_ID_PATTERN.search(latest_content)
                latest_run_id = latest_match.group(1) if latest_match else ""
            assert latest_run_id, latest_metadata
            run_id = latest_run_id

            latest_snapshot = _wait_for_run(client, latest_run_id, run_timeout)
            assert latest_snapshot.get("status") == "completed", latest_snapshot
            latest_spec = latest_snapshot.get("spec")
            assert isinstance(latest_spec, dict), latest_snapshot
            assert latest_spec.get("runtime") == "pi", latest_spec
            assert latest_spec.get("task") == _LATEST_PROMPT, latest_spec
            assert latest_spec.get("objective") == _LATEST_PROMPT, latest_spec
            assert _REVISED_PROMPT not in str(latest_spec.get("task") or "")

            latest_identity_text = (worktree / _TARGET_FILES[0]).read_text(
                encoding="utf-8"
            )
            assert (
                "mode === 'character' ? 'Character settings' : 'Profile'"
                in latest_identity_text
            )
            assert (
                "mode === 'character' ? 'Character settings' : 'Personality'"
                not in latest_identity_text
            )
    finally:
        if run_id:
            try:
                with httpx.Client(base_url=_gateway_url(), timeout=10.0) as cleanup_client:
                    snapshot_response = cleanup_client.get(
                        f"/api/agent-runs/{quote(run_id, safe='')}"
                    )
                    if snapshot_response.is_success and snapshot_response.json().get("status") not in _TERMINAL_RUN_STATUSES:
                        cleanup_client.post(
                            f"/api/agent-runs/{quote(run_id, safe='')}/commands",
                            json={"command_type": "cancel"},
                        )
            except Exception:
                pass
        _remove_isolated_repository(temp_root)
