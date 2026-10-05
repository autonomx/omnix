"""The Claude Code CLI provider runs ``claude -p`` as a plain LLM and parses its stream-json events."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app.providers import claude_cli_provider as module
from app.providers.base import ChatMessage, ProviderConfig, ProviderError
from app.providers.catalog import specs


def _events(*texts: str, result: dict | None = None) -> str:
    rows = [{"type": "system", "subtype": "init", "model": "claude-sonnet-5-5"}]
    rows += [
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}}
        for text in texts
    ]
    rows.append(result or {"type": "result", "is_error": False, "result": "".join(texts), "stop_reason": "end_turn",
                           "usage": {"input_tokens": 12, "output_tokens": 3}})
    return "\n".join(json.dumps(row) for row in rows) + "\n"


class _FakePopen:
    calls: list[dict] = []
    stdout_text = ""

    def __init__(self, command, **kwargs):
        system_file = Path(command[command.index("--system-prompt-file") + 1])
        self.record = {"command": command, "cwd": kwargs["cwd"], "system": system_file.read_text(encoding="utf-8")}
        _FakePopen.calls.append(self.record)
        self.stdin = _Stdin(self.record)
        self.stdout = io.StringIO(_FakePopen.stdout_text)
        self.stderr = io.StringIO("")
        self.returncode = 0

    def wait(self):
        return 0

    def poll(self):
        return 0

    def kill(self):
        pass


class _Stdin(io.StringIO):
    def __init__(self, record):
        super().__init__()
        self.record = record

    def close(self):
        self.record["prompt"] = self.getvalue()
        super().close()


@pytest.fixture
def provider(monkeypatch):
    _FakePopen.calls = []
    monkeypatch.setattr(module, "resolve_claude_executable", lambda _path: "claude")
    monkeypatch.setattr(module.subprocess, "Popen", _FakePopen)
    return module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli", extra_params={"effort": "high"}))


def test_a_call_runs_the_cli_as_a_plain_llm_with_the_omnix_system_prompt(provider) -> None:
    _FakePopen.stdout_text = _events("pong")
    response = provider.chat_completion([ChatMessage("system", "Be terse."), ChatMessage("user", "ping")])

    assert response.content == "pong"
    assert response.model == "claude-sonnet-5-5"
    assert response.usage == {"prompt_tokens": 12, "completion_tokens": 3}
    call = _FakePopen.calls[0]
    command = call["command"]
    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--setting-sources") + 1] == ""
    assert {"--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(command)
    assert command[command.index("--effort") + 1] == "high"
    assert call["system"] == "Be terse." and call["prompt"] == "ping"
    assert not Path(call["cwd"]).exists()  # the empty working directory is removed


def test_streaming_yields_text_deltas_then_a_final_chunk(provider) -> None:
    _FakePopen.stdout_text = _events("one ", "two")
    chunks = list(provider.chat_completion([ChatMessage("user", "count")], stream=True))

    assert [chunk.content for chunk in chunks] == ["one ", "two", ""]
    assert chunks[-1].finish_reason == "end_turn"


def test_a_conversation_and_a_json_contract_reach_the_cli(provider) -> None:
    _FakePopen.stdout_text = _events("{}")
    provider.chat_completion(
        [ChatMessage("system", "Rules."), ChatMessage("user", "hi"), ChatMessage("assistant", "hello"),
         ChatMessage("user", "again")],
        response_format={"type": "json_object"},
    )

    call = _FakePopen.calls[0]
    assert call["prompt"] == "USER: hi\n\nASSISTANT: hello\n\nUSER: again"
    assert call["system"].startswith("Rules.") and "valid JSON object" in call["system"]


def test_a_cli_error_result_is_a_provider_error(provider) -> None:
    _FakePopen.stdout_text = _events(result={"type": "result", "is_error": True, "result": "Not logged in"})
    with pytest.raises(ProviderError, match="Not logged in"):
        provider.chat_completion([ChatMessage("user", "ping")])


def test_the_provider_is_in_the_llm_catalog_and_needs_no_api_key() -> None:
    assert "claude_cli" in {spec.id for spec in specs("llm")}
    assert next(spec for spec in specs("llm") if spec.id == "claude_cli").load() is module.ClaudeCliProvider
    assert module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli")).requires_api_key() is False
    with pytest.raises(ValueError, match="effort"):
        module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli", extra_params={"effort": "turbo"}))
