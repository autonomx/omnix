"""The Claude Code CLI provider runs ``claude -p`` as a plain LLM and parses its stream-json events."""
from __future__ import annotations

import io
import json
import threading
import time
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
        self.record = {"command": command, "cwd": kwargs["cwd"], "env": kwargs["env"],
                       "system": system_file.read_text(encoding="utf-8")}
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
        # The prompt goes in as one stream-json user message.
        message = json.loads(self.getvalue())
        assert message["type"] == "user" and message["message"]["role"] == "user"
        self.record["prompt"] = message["message"]["content"]
        super().close()


@pytest.fixture
def provider(monkeypatch):
    _FakePopen.calls = []
    monkeypatch.setattr(module, "resolve_claude_executable", lambda _path: "claude")
    monkeypatch.setattr(module.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(module, "_WARM_POOL", module._WarmPool())
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
    assert command[command.index("--input-format") + 1] == "stream-json"
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


def test_the_models_are_the_clis_catalog_then_the_aliases() -> None:
    models = module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli")).get_models()
    ids = [model.id for model in models]
    assert ids[:4] == ["claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5-5", "claude-haiku-5-5"]
    assert ids[-4:] == ["sonnet", "opus", "haiku", "fable"]
    assert len(ids) == len(set(ids)) == len(module.CLAUDE_CLI_MODELS) + 4
    assert models[0].name == "Opus 5.5" and models[-4].name == "Latest Sonnet (sonnet)"
    custom = module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli", model="claude-custom-1")).get_models()
    assert custom[0].id == "claude-custom-1" and len(custom) == len(models) + 1


def test_the_model_catalog_lists_every_claude_cli_model_for_the_chat_model_picker() -> None:
    from types import SimpleNamespace

    from app.providers.facade import ProviderFacade

    settings = {"settings_control_center": {"providerConfigs": {"claudeCli": {"model": "opus"}}}}
    facade = ProviderFacade(settings_loader=lambda: settings, llm_lister=lambda: [], tts_lister=lambda: [])
    models = [model for model in facade.list_configured_models([SimpleNamespace(id="llm:claude_cli")])
              if model.provider_id == "llm:claude_cli"]
    assert [model.id for model in models[:2]] == ["llm:claude_cli:claude-opus-5-5", "llm:claude_cli:claude-fable-5-1"]
    assert models[0].label == "Opus 5.5" and models[0].metadata["model_id"] == "claude-opus-5-5"
    assert [model.metadata["model_id"] for model in models if model.metadata["configured"]] == ["opus"]
    assert len(models) == len(module.CLAUDE_CLI_MODELS) + 4


def test_a_json_schema_goes_to_the_cli_and_its_structured_output_is_the_answer(provider) -> None:
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    _FakePopen.stdout_text = _events("Here is the JSON:", result={
        "type": "result", "is_error": False, "result": '{"name": "Inn"}', "structured_output": {"name": "Inn"},
        "stop_reason": "end_turn", "usage": {}})
    response_format = {"type": "json_schema", "json_schema": {"name": "x", "schema": schema}}

    response = provider.chat_completion([ChatMessage("user", "name it")], response_format=response_format)
    streamed = list(provider.chat_completion([ChatMessage("user", "name it")], stream=True, response_format=response_format))

    assert response.content == '{"name": "Inn"}'
    assert [chunk.content for chunk in streamed] == ['{"name": "Inn"}']
    command = _FakePopen.calls[0]["command"]
    assert json.loads(command[command.index("--json-schema") + 1]) == schema
    assert "JSON Schema" in _FakePopen.calls[0]["system"]


class _WaitingPopen(_FakePopen):
    """A process that keeps running until its prompt arrives, like a started ``claude -p`` waiting on stdin."""

    killed: list["_WaitingPopen"] = []

    def __init__(self, command, **kwargs):
        super().__init__(command, **kwargs)
        self.alive = True

    def poll(self):
        return None if self.alive and "prompt" not in self.record else 0

    def kill(self):
        self.alive = False
        _WaitingPopen.killed.append(self)

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def pooled(monkeypatch):
    _FakePopen.calls = []
    _WaitingPopen.killed = []
    monkeypatch.setattr(module, "resolve_claude_executable", lambda _path: "claude")
    monkeypatch.setattr(module.subprocess, "Popen", _WaitingPopen)
    pool = module._WarmPool()
    monkeypatch.setattr(module, "_WARM_POOL", pool)
    _FakePopen.stdout_text = _events("ok")
    return module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli")), pool


def test_a_repeated_kind_of_call_takes_a_process_started_ahead_of_it(pooled) -> None:
    provider, pool = pooled
    ask = lambda text, system="Narrate.": provider.chat_completion([ChatMessage("system", system), ChatMessage("user", text)])  # noqa: E731

    ask("first")
    assert len(_FakePopen.calls) == 1  # a first call of its kind leaves nothing waiting
    ask("second")
    assert len(_FakePopen.calls) == 3  # the second starts the next one ahead
    waiting = _FakePopen.calls[2]
    assert "prompt" not in waiting
    ask("third")
    assert waiting["prompt"] == "third"  # the third call answered from the waiting process
    assert len(_FakePopen.calls) == 4
    # Another kind (another system prompt) does not take it.
    ask("other", system="Summarize.")
    assert _FakePopen.calls[4]["prompt"] == "other"
    pool.close()
    assert all(not process.alive for process in _WaitingPopen.killed)


def test_the_pool_keeps_few_processes_and_retires_idle_ones(pooled) -> None:
    provider, pool = pooled
    pool.IDLE_SECONDS = 2.0  # long enough for the calls below on a busy machine
    for system in ("A", "B", "C", "D"):
        for _ in range(2):
            provider.chat_completion([ChatMessage("system", system), ChatMessage("user", "hi")])
    assert len(pool._warm) == pool.MAX_WARM  # the oldest waiting process made room
    assert len(_WaitingPopen.killed) == 1
    deadline = time.monotonic() + 10
    while (pool._warm or len(_WaitingPopen.killed) < 4) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pool._warm == {}  # idle ones are retired
    assert len(_WaitingPopen.killed) == 4
    assert all(not Path(record["cwd"]).exists() for record in _FakePopen.calls)


def test_a_spoken_turn_answers_without_thinking_and_no_other_call_does(provider) -> None:
    _FakePopen.stdout_text = _events("ok")
    provider.chat_completion([ChatMessage("user", "typed")])
    _FakePopen.stdout_text = _events("ok")
    provider.chat_completion([ChatMessage("user", "spoken")], live_turn=True)

    typed = next(call for call in _FakePopen.calls if call.get("prompt") == "typed")
    spoken = next(call for call in _FakePopen.calls if call.get("prompt") == "spoken")
    assert "MAX_THINKING_TOKENS" not in typed["env"]
    assert spoken["env"]["MAX_THINKING_TOKENS"] == "0"
    # The configured effort stays: thinking off does not depend on it.
    assert spoken["command"][spoken["command"].index("--effort") + 1] == "high"


def test_every_turn_of_a_call_takes_a_waiting_process_though_its_context_changes(pooled) -> None:
    provider, pool = pooled
    def turn(memory: str, text: str) -> list[ChatMessage]:
        return [ChatMessage("system", "You are Aria."), ChatMessage("system", memory, per_turn=True),
                ChatMessage("user", text)]

    provider.warm_live_turn(turn("Memory for the warm-up.", "warm-up"), model="claude-haiku-4-5-20251001")
    assert len(_FakePopen.calls) == 1  # started on the first ask, with no request and no earlier uses
    waiting = _FakePopen.calls[0]
    assert "prompt" not in waiting and waiting["env"]["MAX_THINKING_TOKENS"] == "0"
    assert waiting["system"] == "You are Aria."

    provider.chat_completion(turn("Likes tea.", "hello"), model="claude-haiku-4-5-20251001", live_turn=True)
    assert len(_FakePopen.calls) == 2  # the turn took it, and the next one is already started
    assert waiting["prompt"] == "Context for this turn, not said by anyone:\n\nLikes tea.\n\nUSER: hello"
    next_waiting = _FakePopen.calls[1]

    provider.chat_completion(turn("Likes coffee now.", "again"), model="claude-haiku-4-5-20251001", live_turn=True)
    assert len(_FakePopen.calls) == 3
    assert next_waiting["prompt"].endswith("Likes coffee now.\n\nUSER: again")
    pool.close()


def test_a_live_turn_logs_whether_a_process_was_waiting_and_no_text(pooled, monkeypatch) -> None:
    provider, pool = pooled
    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(module, "stream_log", lambda _stream, _source, event, **fields: logged.append((event, fields)))
    messages = [ChatMessage("system", "You are Aria.\n\nSpeak briefly."), ChatMessage("user", "hello there")]

    provider.chat_completion(messages, live_turn=True)  # nothing was warmed: this one starts its own
    provider.chat_completion(messages, live_turn=True)
    provider.warm_live_turn([ChatMessage("system", "You are Aria.\n\nSpeak differently."), ChatMessage("user", "x")])
    provider.chat_completion(messages)  # not a live turn: not logged
    pool.close()

    turns = [fields for event, fields in logged if event == "claude_cli_live_turn"]
    assert [fields["waiting_process"] for fields in turns] == [False, True]
    warmed = next(fields for event, fields in logged if event == "claude_cli_process_warmed")
    assert warmed["kind"] != turns[0]["kind"]  # the warm-up's prompt differs: it is a different kind of call
    # A diff of the parts' hashes says which part of the prompt moved; the log holds no text.
    assert warmed["system_parts"][0] == turns[0]["system_parts"][0]
    assert warmed["system_parts"][1] != turns[0]["system_parts"][1]
    assert "Aria" not in json.dumps(logged) and "hello" not in json.dumps(logged)


def test_a_spoken_turn_does_not_take_a_process_started_for_another_kind_of_call(pooled) -> None:
    provider, pool = pooled
    messages = [ChatMessage("system", "Same system."), ChatMessage("user", "hi")]
    provider.warm_live_turn(messages)
    provider.chat_completion(messages)  # thinking stays on for this one, so it starts its own process

    assert len(_FakePopen.calls) == 2
    assert _FakePopen.calls[0].get("prompt") is None
    assert "MAX_THINKING_TOKENS" not in _FakePopen.calls[1]["env"]
    pool.close()


def test_a_live_process_waits_through_a_call_and_is_retired_after_it(pooled, monkeypatch) -> None:
    provider, pool = pooled
    limits: list[tuple[float, tuple]] = []

    class _Timer:
        def __init__(self, seconds, _function, args=()):
            limits.append((seconds, args))
            self.daemon = True

        def start(self):
            pass

    monkeypatch.setattr(module.threading, "Timer", _Timer)
    provider.warm_live_turn([ChatMessage("system", "You are Aria."), ChatMessage("user", "warm-up")])

    (seconds, (kind, process)), = limits
    assert seconds == pool.LIVE_IDLE_SECONDS > pool.IDLE_SECONDS
    assert len(pool._warm) == 1
    pool._expire(kind, process)
    assert pool._warm == {}
    assert len(_WaitingPopen.killed) == 1


class _StreamingPopen(_WaitingPopen):
    """A process still writing its reply when the caller stops reading."""

    def poll(self):
        return None if self.alive else 0


def test_stopping_reading_a_reply_ends_the_cli_call(monkeypatch) -> None:
    _FakePopen.calls = []
    _WaitingPopen.killed = []
    monkeypatch.setattr(module, "resolve_claude_executable", lambda _path: "claude")
    monkeypatch.setattr(module.subprocess, "Popen", _StreamingPopen)
    monkeypatch.setattr(module, "_WARM_POOL", module._WarmPool())
    _FakePopen.stdout_text = _events("one ", "two")
    provider = module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli"))

    stream = provider.chat_completion([ChatMessage("user", "go")], stream=True)
    assert next(stream).content == "one "
    stream.close()

    assert len(_WaitingPopen.killed) == 1
    assert not Path(_FakePopen.calls[0]["cwd"]).exists()


class _StderrUntilKilled:
    """A real process's stderr: reading it ends only when the process does."""

    def __init__(self) -> None:
        self.ended = threading.Event()

    def read(self) -> str:
        self.ended.wait(timeout=10)
        return ""


class _RunningPopen(_StreamingPopen):
    def __init__(self, command, **kwargs):
        super().__init__(command, **kwargs)
        self.stderr = _StderrUntilKilled()

    def kill(self):
        self.stderr.ended.set()
        super().kill()


def test_stopping_reading_ends_the_call_at_once(monkeypatch) -> None:
    # Real: stderr was awaited before the kill, so every stopped call took a second longer than it needed. A judgement
    # of speech over a reply missed its deadline by that second, every time.
    _FakePopen.calls = []
    _WaitingPopen.killed = []
    monkeypatch.setattr(module, "resolve_claude_executable", lambda _path: "claude")
    monkeypatch.setattr(module.subprocess, "Popen", _RunningPopen)
    monkeypatch.setattr(module, "_WARM_POOL", module._WarmPool())
    _FakePopen.stdout_text = _events("one ", "two")
    provider = module.ClaudeCliProvider(ProviderConfig(provider_type="claude_cli"))

    stream = provider.chat_completion([ChatMessage("user", "go")], stream=True)
    next(stream)
    started = time.perf_counter()
    stream.close()

    assert time.perf_counter() - started < 0.5


def test_a_schema_call_streams_its_structured_answer_as_it_is_written(provider) -> None:
    rows = [
        {"type": "stream_event", "event": {"type": "content_block_delta",
                                           "delta": {"type": "input_json_delta", "partial_json": '{"blocks": [{"te'}}},
        {"type": "stream_event", "event": {"type": "content_block_delta",
                                           "delta": {"type": "input_json_delta", "partial_json": 'xt": "Hi"}]}'}}},
        {"type": "result", "is_error": False, "structured_output": {"blocks": [{"text": "Hi"}]}, "stop_reason": "end_turn"},
    ]
    _FakePopen.stdout_text = "\n".join(json.dumps(row) for row in rows) + "\n"
    schema_format = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}
    chunks = list(provider.chat_completion([ChatMessage("user", "go")], stream=True, response_format=schema_format))

    assert [chunk.raw_response.get("structured_delta") for chunk in chunks[:-1]] == ['{"blocks": [{"te', 'xt": "Hi"}]}']
    assert all(chunk.content == "" for chunk in chunks[:-1])
    assert json.loads(chunks[-1].content) == {"blocks": [{"text": "Hi"}]}
    # A plain call still answers with the validated structured output only.
    _FakePopen.stdout_text = "\n".join(json.dumps(row) for row in rows) + "\n"
    answer = provider.chat_completion([ChatMessage("user", "go")], response_format=schema_format)
    assert json.loads(answer.content) == {"blocks": [{"text": "Hi"}]}
