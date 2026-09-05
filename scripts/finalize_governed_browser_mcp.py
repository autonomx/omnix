from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Browser origin normalization and deterministic assertion actions.
replace_once(
    "src/app/assistant_tools/browser_adapter.py",
    '_DEFAULT_ALLOWED_DOMAINS = ("localhost", "127.0.0.1", "[::1]")',
    '_DEFAULT_ALLOWED_DOMAINS = ("localhost", "127.0.0.1", "::1")',
)
replace_once(
    "src/app/assistant_tools/browser_adapter.py",
    '''    "browser.screenshot",\n    "browser.close",\n}\n_INTERACTIVE = {''',
    '''    "browser.screenshot",\n    "browser.assert_text_contains",\n    "browser.assert_attribute_contains",\n    "browser.assert_url_contains",\n    "browser.close",\n}\n_ASSERTIONS = {\n    "browser.assert_text_contains",\n    "browser.assert_attribute_contains",\n    "browser.assert_url_contains",\n}\n_INTERACTIVE = {''',
)
replace_once(
    "src/app/assistant_tools/browser_adapter.py",
    '''    elif action == "browser.screenshot":\n        directory = Path(tempfile.gettempdir()) / "omnix-agent-browser"\n        directory.mkdir(parents=True, exist_ok=True)\n        target = directory / f"{_session_name(request.session_id)}-{os.urandom(6).hex()}.png"\n        argv.extend(["screenshot", str(target)])\n        if bool(payload.get("full_page")):\n            argv.append("--full")\n        metadata["screenshot_path"] = str(target)\n    elif action == "browser.close":''',
    '''    elif action == "browser.screenshot":\n        directory = Path(tempfile.gettempdir()) / "omnix-agent-browser"\n        directory.mkdir(parents=True, exist_ok=True)\n        target = directory / f"{_session_name(request.session_id)}-{os.urandom(6).hex()}.png"\n        argv.extend(["screenshot", str(target)])\n        if bool(payload.get("full_page")):\n            argv.append("--full")\n        metadata["screenshot_path"] = str(target)\n    elif action == "browser.assert_text_contains":\n        argv.extend(["get", "text", _safe_selector(payload.get("selector"))])\n        metadata["assertion_expected"] = _safe_text(\n            payload.get("expected"), field="expected text", max_chars=4096\n        )\n    elif action == "browser.assert_attribute_contains":\n        argv.extend([\n            "get",\n            "attr",\n            _safe_selector(payload.get("selector")),\n            _safe_text(payload.get("attribute"), field="attribute", max_chars=256),\n        ])\n        metadata["assertion_expected"] = _safe_text(\n            payload.get("expected"), field="expected attribute", max_chars=4096\n        )\n    elif action == "browser.assert_url_contains":\n        argv.extend(["get", "url"])\n        metadata["assertion_expected"] = _safe_text(\n            payload.get("expected"), field="expected URL", max_chars=4096\n        )\n    elif action == "browser.close":''',
)
replace_once(
    "src/app/assistant_tools/browser_adapter.py",
    '''    stdout = (completed.stdout or "")[:_MAX_OUTPUT_CHARS]\n    stderr = (completed.stderr or "")[:8_000]\n    if completed.returncode != 0:\n        return AssistantToolResult(''',
    '''    stdout = (completed.stdout or "")[:_MAX_OUTPUT_CHARS]\n    stderr = (completed.stderr or "")[:8_000]\n    if completed.returncode != 0:\n        return AssistantToolResult(''',
)
replace_once(
    "src/app/assistant_tools/browser_adapter.py",
    '''    output: dict[str, Any] = {"stdout": stdout, **metadata}\n    if request.action_id == "browser.snapshot" and stdout.strip():''',
    '''    output: dict[str, Any] = {"stdout": stdout, **metadata}\n    if request.action_id in _ASSERTIONS:\n        expected = str(metadata.get("assertion_expected") or "")\n        if expected not in stdout:\n            return AssistantToolResult(\n                tool_id="browser",\n                action_id=request.action_id,\n                session_id=request.session_id,\n                state_changed=False,\n                result_summary=f"Browser assertion failed for {request.action_id}.",\n                output=output,\n                error="browser_assertion_failed",\n            )\n        output["assertion_passed"] = True\n    if request.action_id == "browser.snapshot" and stdout.strip():''',
)

# Canonical MCP action grammar consistency.
replace_once(
    "src/app/assistant_tools/validation.py",
    'r"^mcp\\.[a-z][a-z0-9_]{1,63}\\.[a-z][a-z0-9_]{1,63}$"',
    'r"^mcp\\.[a-z][a-z0-9_]{0,63}\\.[a-z][a-z0-9_]{0,63}$"',
)

# Generic MCP text never grants every configured tool when multiple servers exist.
replace_once(
    "src/app/agent_runtime/mcp_policy.py",
    '''    if re.search(r"\\b(?:mcp|mcporter|model\\s+context\\s+protocol)\\b", text, re.I):\n        return tuple(tool.capability_id for _server, tool in rows)\n    matched: list[str] = []\n    for server, tool in rows:\n        candidates = (\n            server.name.casefold(),\n            tool.name.casefold(),\n            tool.capability_id.casefold(),\n        )\n        if any(candidate and candidate in folded for candidate in candidates):\n            matched.append(tool.capability_id)\n    return tuple(dict.fromkeys(matched))''',
    '''    matched: list[str] = []\n    for server, tool in rows:\n        candidates = (\n            server.name.casefold(),\n            tool.name.casefold(),\n            tool.capability_id.casefold(),\n        )\n        if any(candidate and candidate in folded for candidate in candidates):\n            matched.append(tool.capability_id)\n    if matched:\n        return tuple(dict.fromkeys(matched))\n\n    # A generic "use MCP" request is only unambiguous when exactly one server\n    # is configured. With multiple configured servers, require the prompt to\n    # name a server/tool/capability rather than issuing the union of authority.\n    generic_use = re.search(\n        r"(?:\\b(?:use|via|through|with|call|invoke|query|access)\\b.{0,80}"\n        r"\\b(?:mcp|mcporter|model\\s+context\\s+protocol)\\b|"\n        r"\\b(?:mcp|mcporter|model\\s+context\\s+protocol)\\b.{0,80}"\n        r"\\b(?:use|call|invoke|query|access)\\b)",\n        text,\n        re.I,\n    )\n    server_names = {server.name for server, _tool in rows}\n    if generic_use and len(server_names) == 1:\n        only_server = next(iter(server_names))\n        return tuple(\n            tool.capability_id\n            for server, tool in rows\n            if server.name == only_server\n        )\n    return ()''',
)

# Browser assertions are canonical coding capabilities but remain coding-only.
replace_once(
    "src/app/agent_runtime/capabilities.py",
    '''    _cap("browser.screenshot", "Capture browser screenshot", "Capture screenshot evidence from the governed browser session.", zone="broker", effect="read", network=True, connection=True, provider="agent-browser", category="development", assistant=True, input_schema={"full_page": "optional boolean"}),\n    _cap("browser.close",''',
    '''    _cap("browser.screenshot", "Capture browser screenshot", "Capture screenshot evidence from the governed browser session.", zone="broker", effect="read", network=True, connection=True, provider="agent-browser", category="development", assistant=True, input_schema={"full_page": "optional boolean"}),\n    _cap("browser.assert_text_contains", "Assert browser text", "Deterministically require an element's text to contain an expected value.", zone="broker", effect="read", network=True, connection=True, provider="agent-browser", category="development", assistant=True, input_schema={"selector": "agent-browser selector or @ref", "expected": "required text substring"}),\n    _cap("browser.assert_attribute_contains", "Assert browser attribute", "Deterministically require one DOM attribute to contain an expected value.", zone="broker", effect="read", network=True, connection=True, provider="agent-browser", category="development", assistant=True, input_schema={"selector": "agent-browser selector or @ref", "attribute": "attribute name", "expected": "required substring"}),\n    _cap("browser.assert_url_contains", "Assert browser URL", "Deterministically require the active browser URL to contain an expected value.", zone="broker", effect="read", network=True, connection=True, provider="agent-browser", category="development", assistant=True, input_schema={"expected": "required URL substring"}),\n    _cap("browser.close",''',
)
replace_once(
    "src/app/agent_runtime/profiles.py",
    '''    "browser.screenshot",\n    "browser.close",''',
    '''    "browser.screenshot",\n    "browser.assert_text_contains",\n    "browser.assert_attribute_contains",\n    "browser.assert_url_contains",\n    "browser.close",''',
)

# Browser validation becomes first-class state-bound quality evidence.
replace_once(
    "src/app/agent_runtime/contracts.py",
    'ValidationKind = Literal["test", "typecheck", "lint", "build", "diff_review", "custom"]',
    'ValidationKind = Literal["test", "typecheck", "lint", "build", "diff_review", "browser", "custom"]',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''_WEB = re.compile(r"\\b(?:react|typescript|tsx|jsx|frontend|web|css|ui|theme|light\\s*mode|dark\\s*mode)\\b", re.I)\n_CRITICAL = re.compile(''',
    '''_WEB = re.compile(r"\\b(?:react|typescript|tsx|jsx|frontend|web|css|ui|theme|light\\s*mode|dark\\s*mode)\\b", re.I)\n_BROWSER_VALIDATION = re.compile(\n    r"\\b(?:agent[- ]browser|browser\\s+(?:test|testing|validation|verify|verification)|"\n    r"e2e|end[- ]to[- ]end|playwright|visual\\s+(?:test|testing|validation|regression)|"\n    r"click\\s+through|interact\\s+with\\s+(?:the\\s+)?(?:page|ui|app))\\b",\n    re.I,\n)\n_BROWSER_ASSERTIONS = {\n    "browser.assert_text_contains",\n    "browser.assert_attribute_contains",\n    "browser.assert_url_contains",\n}\n_CRITICAL = re.compile(''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        if _WEB.search(objective_text):\n            validation.append(\n                ValidationSpec(\n                    id="frontend-build-or-typecheck",\n                    kind="build",\n                    description="Run a frontend build or typecheck when the changed surface is web/UI code.",\n                    covers=["user-objective", "derived-regression-safety"],\n                    required=False,\n                    command_hint="npm --prefix src/apps/web run build",\n                )\n            )\n''',
    '''        if _WEB.search(objective_text):\n            validation.append(\n                ValidationSpec(\n                    id="frontend-build-or-typecheck",\n                    kind="build",\n                    description="Run a frontend build or typecheck when the changed surface is web/UI code.",\n                    covers=["user-objective", "derived-regression-safety"],\n                    required=False,\n                    command_hint="npm --prefix src/apps/web run build",\n                )\n            )\n            validation.append(\n                ValidationSpec(\n                    id="browser-validation",\n                    kind="browser",\n                    description=(\n                        "Exercise the changed UI through the governed browser and prove an expected final state "\n                        "with browser.assert_text_contains, browser.assert_attribute_contains, or "\n                        "browser.assert_url_contains."\n                    ),\n                    covers=["user-objective", "derived-regression-safety"],\n                    required=bool(_BROWSER_VALIDATION.search(objective_text)),\n                    command_hint="Use governed browser.* capabilities via omnix_capability",\n                )\n            )\n''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        "build": "frontend-build-or-typecheck",\n    }.get(kind, f"observed-{kind}")''',
    '''        "build": "frontend-build-or-typecheck",\n        "browser": "browser-validation",\n    }.get(kind, f"observed-{kind}")''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''    args = event.payload.get("args") if isinstance(event.payload.get("args"), dict) else {}\n    command = str(args.get("command") or event.payload.get("command") or "").strip()\n    kind = validation_kind_for_command(command)\n    if kind is None:\n        return None\n    success = not bool(event.payload.get("is_error"))\n''',
    '''    args = event.payload.get("args") if isinstance(event.payload.get("args"), dict) else {}\n    capability_id = str(args.get("capability_id") or event.payload.get("capability_id") or "").strip()\n    command = str(args.get("command") or event.payload.get("command") or "").strip()\n    if capability_id in _BROWSER_ASSERTIONS:\n        kind = "browser"\n        command = f"omnix_capability {capability_id}"\n    else:\n        kind = validation_kind_for_command(command)\n    if kind is None:\n        return None\n    success = not bool(event.payload.get("is_error")) and not bool(event.payload.get("error"))\n''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''    if isinstance(result, dict):\n        details = result.get("details") if isinstance(result.get("details"), dict) else result\n        raw_exit = details.get("exitCode", details.get("exit_code"))\n        if raw_exit is not None:\n            try:\n                exit_code = int(raw_exit)\n                success = success and exit_code == 0\n            except (TypeError, ValueError):\n                success = False\n''',
    '''    if isinstance(result, dict):\n        details = result.get("details") if isinstance(result.get("details"), dict) else result\n        raw_exit = details.get("exitCode", details.get("exit_code"))\n        if raw_exit is not None:\n            try:\n                exit_code = int(raw_exit)\n                success = success and exit_code == 0\n            except (TypeError, ValueError):\n                success = False\n        if kind == "browser":\n            broker = details if "executed" in details else details.get("result")\n            if isinstance(broker, dict):\n                if broker.get("executed") is False or broker.get("error"):\n                    success = False\n                nested = broker.get("result")\n                if isinstance(nested, dict) and nested.get("error"):\n                    success = False\n''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        metadata={"tool_call_id": call_id},\n    )''',
    '''        metadata={"tool_call_id": call_id, "capability_id": capability_id or None},\n    )''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        "Do not substitute an unrelated passing test."\n    )''',
    '''        "Do not substitute an unrelated passing test. For browser validation, interact with the governed "\n        "browser as needed and finish with a deterministic browser.assert_* capability that proves the expected "\n        "final state; a screenshot or snapshot alone is not completion evidence."\n    )''',
)

# Documentation must use canonical capability ids and list assertion tools.
replace_once(
    "docs/agent-runtime-browser-mcp.md",
    "mcp.context7.resolve-library-id",
    "mcp.context7.resolve_library_id",
)
replace_once(
    "docs/agent-runtime-browser-mcp.md",
    '''- `browser.screenshot`\n- `browser.close`''',
    '''- `browser.screenshot`\n- `browser.assert_text_contains`\n- `browser.assert_attribute_contains`\n- `browser.assert_url_contains`\n- `browser.close`''',
)

# Focused tests for deterministic browser evidence and least-authority MCP inference.
test_path = Path("src/tests/agent_runtime/test_governed_browser_mcp.py")
test_text = test_path.read_text(encoding="utf-8")
if "test_browser_assertion_becomes_state_bound_validation" not in test_text:
    test_text += r'''


def test_browser_assertion_passes_and_failure_is_not_execution_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)

    monkeypatch.setattr(
        browser_adapter,
        "_run",
        lambda argv: subprocess.CompletedProcess(argv, 0, stdout="Score: 20 / 20", stderr=""),
    )
    passed = browser_adapter.run_browser_tool_request(
        AssistantToolRequest(
            tool_id="browser",
            action_id="browser.assert_text_contains",
            session_id="run-browser-assert",
            input={"selector": "#score", "expected": "20 / 20"},
        )
    )
    assert passed.error is None
    assert passed.output["assertion_passed"] is True

    failed = browser_adapter.run_browser_tool_request(
        AssistantToolRequest(
            tool_id="browser",
            action_id="browser.assert_text_contains",
            session_id="run-browser-assert",
            input={"selector": "#score", "expected": "19 / 20"},
        )
    )
    assert failed.error == "browser_assertion_failed"


def test_browser_assertion_becomes_state_bound_validation() -> None:
    from app.agent_runtime.coding_quality import (
        compile_task_engineering_contract,
        validation_result_from_tool_event,
    )
    from app.agent_runtime.contracts import AgentEvent, TaskRevision

    requirements, constraints, plan = compile_task_engineering_contract(
        "Fix the React quiz and verify it with browser testing",
        [],
        profile="coding",
        mutating=True,
    )
    browser_spec = next(item for item in plan if item.id == "browser-validation")
    assert browser_spec.kind == "browser"
    assert browser_spec.required is True
    revision = TaskRevision(
        run_id="run-browser-quality",
        sequence=1,
        user_instruction="Fix the React quiz and verify it with browser testing",
        effective_objective="Fix the React quiz and verify it with browser testing",
        requirements=requirements,
        constraints=constraints,
        validation_plan=plan,
    )
    event = AgentEvent(
        run_id="run-browser-quality",
        event_type="tool.completed",
        payload={
            "tool_call_id": "browser-proof-1",
            "args": {
                "capability_id": "browser.assert_text_contains",
                "input": {"selector": "#score", "expected": "20 / 20"},
            },
            "result": {"details": {"executed": True, "result": {"error": None}}},
        },
    )
    result = validation_result_from_tool_event(
        event,
        run_id="run-browser-quality",
        task_revision_id=revision.revision_id,
        workspace_state_id="state-final",
        revision=revision,
    )
    assert result is not None
    assert result.kind == "browser"
    assert result.validation_id == "browser-validation"
    assert result.workspace_state_id == "state-final"
    assert result.task_revision_id == revision.revision_id
    assert result.success is True
    assert set(browser_spec.covers).issubset(result.covers_requirement_ids)


def test_generic_mcp_reference_does_not_union_multiple_servers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = tmp_path / "multi-policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": [
                    {
                        "name": "docs",
                        "transport": "http",
                        "url": "https://docs.example.test/mcp",
                        "tools": [
                            {"name": "search", "capability_id": "mcp.docs.search"}
                        ],
                    },
                    {
                        "name": "issues",
                        "transport": "http",
                        "url": "https://issues.example.test/mcp",
                        "tools": [
                            {"name": "lookup", "capability_id": "mcp.issues.lookup"}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNIX_AGENT_MCP_POLICY_PATH", str(policy))
    assert coding_external_capabilities_for_task("Use MCP while implementing this") == ()
    assert coding_external_capabilities_for_task("Use the docs MCP server") == (
        "mcp.docs.search",
    )
'''
    test_path.write_text(test_text, encoding="utf-8")
