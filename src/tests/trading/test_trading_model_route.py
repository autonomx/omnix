"""The Trading model setting, and what trading sends a local model."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.apps.trading import model_route, strategy_ai_shadow_provider as lane, strategy_intraday_llm
from app.apps.trading.evidence_storage import MemoryEvidenceBackend
from app.apps.trading.research import default_research_provider
from app.apps.trading.research.market_research import _call_provider
from app.apps.trading.strategy_ai_shadow import AIShadowPolicyAnalyzer, _build_payload
from app.apps.trading.structured_llm import sends_json_schema, trading_model_call
from app.apps.trading.trading_ai_budget import TradingAIBudget, default_trading_ai_budget
from app.providers import ChatMessage
from app.providers.base import ChatResponse, ProviderConfig
from app.providers.catalog import THINKING_OFF, provider_supports
from app.providers.lmstudio_provider import LMStudioProvider

SHADOW = "trading.ai_shadow_v3.batch"


def _setting(monkeypatch, row: dict | None) -> None:
    overrides = {} if row is None else {model_route.TRADING_ROUTE_KEY: row}
    profile = SimpleNamespace(global_settings=SimpleNamespace(routing=SimpleNamespace(task_overrides=overrides)))
    monkeypatch.setattr("app.settings.effective_defaults.load_effective_profile", lambda: profile)


def _instance(name: str, model: str = "configured") -> SimpleNamespace:
    return SimpleNamespace(
        provider_name=name, config=ProviderConfig(provider_type=name, model=model), loaded_model_key=lambda: model,
    )


@pytest.fixture
def providers(monkeypatch):
    from app.providers import service as provider_service

    asked: list[tuple] = []

    def get_provider(name=None):
        asked.append(("default", name))
        return _instance("claude_cli")

    def get_routed_provider(name, model):
        asked.append(("routed", name, model))
        return _instance(name or "claude_cli", model or "configured")

    monkeypatch.setattr(provider_service, "get_provider", get_provider)
    monkeypatch.setattr(provider_service, "get_routed_provider", get_routed_provider)
    return asked


def test_unset_keeps_the_default_provider(monkeypatch, providers) -> None:
    _setting(monkeypatch, None)

    assert default_research_provider().provider_name == "claude_cli"
    assert providers == [("default", None)]


def test_the_setting_names_the_provider_and_model_of_every_research_entry_point(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "llm:lmstudio", "modelId": "qwen/qwen3.8-27b"})
    built: list[ProviderConfig] = []

    def create_provider(name, provider_config):
        built.append(provider_config)
        return _instance(name, provider_config.model)

    monkeypatch.setattr(lane, "get_registry", lambda: SimpleNamespace(create_provider=create_provider))
    lane.reset_ai_shadow_reliability_state()
    try:
        research = default_research_provider()
        dedicated = lane.get_trading_research_provider()
        intraday = strategy_intraday_llm._default_provider()
    finally:
        lane.reset_ai_shadow_reliability_state()

    assert research.config.model == dedicated.config.model == "qwen/qwen3.8-27b"
    assert providers == [("routed", "lmstudio", "qwen/qwen3.8-27b")] * 3
    assert intraday.provider_name == "lmstudio"
    assert len(built) == 1  # the dedicated lane builds its own instance, away from foreground traffic


def test_lm_studio_without_a_model_follows_what_is_loaded(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "lmstudio", "modelId": ""})
    from app.providers import service as provider_service

    asked: list[str | None] = []

    def routed(name, model):
        asked.append(model)
        instance = _instance(name, model or "stale-configured")
        instance.loaded_model_key = lambda: "qwen/qwen3.8-27b"
        return instance

    monkeypatch.setattr(provider_service, "get_routed_provider", routed)

    assert model_route.trading_provider().config.model == "qwen/qwen3.8-27b"
    assert asked == [None, "qwen/qwen3.8-27b"]


def test_lm_studio_with_nothing_loaded_keeps_its_configured_model(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "lmstudio", "modelId": ""})
    from app.providers import service as provider_service

    def routed(name, model):
        instance = _instance(name, model or "configured")
        instance.loaded_model_key = lambda: None
        return instance

    monkeypatch.setattr(provider_service, "get_routed_provider", routed)

    assert model_route.trading_provider().config.model == "configured"


class _Listing:
    def __init__(self, payload) -> None:
        self.payload = payload

    def json(self):
        return self.payload

    def close(self) -> None:
        pass


def _provider_listing(payload) -> LMStudioProvider:
    provider = LMStudioProvider(ProviderConfig(provider_type="lmstudio", base_url="http://127.0.0.1:1234", model="m"))

    def make_request(method, endpoint, **_):
        assert (method, endpoint) == ("get", "/api/v1/models")
        if isinstance(payload, Exception):
            raise payload
        return _Listing(payload)

    provider._make_request = make_request
    return provider


def test_lm_studio_names_its_loaded_chat_model() -> None:
    provider = _provider_listing({"models": [
        {"type": "embedding", "key": "nomic", "loaded_instances": [{"id": "nomic"}]},
        {"type": "llm", "key": "gemma", "loaded_instances": []},
        {"type": "llm", "key": "qwen/qwen3.8-27b", "loaded_instances": [{"id": "custom-id"}]},
    ]})

    assert provider.loaded_model_key() == "qwen/qwen3.8-27b"


@pytest.mark.parametrize("payload", [{"models": []}, {"unexpected": 1}, ConnectionError("down"), ["not", "a", "dict"]])
def test_lm_studio_names_no_model_when_none_can_be_found(payload) -> None:
    assert _provider_listing(payload).loaded_model_key() is None


def test_a_settings_list_model_id_becomes_the_model_name(monkeypatch) -> None:
    _setting(monkeypatch, {"providerId": "llm:lmstudio", "modelId": "llm:lmstudio:qwen/qwen3.8-27b"})

    assert model_route.trading_model() == model_route.TradingModel("lmstudio", "qwen/qwen3.8-27b")


def test_an_unreadable_setting_falls_back_to_the_default(monkeypatch, providers) -> None:
    def broken():
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr("app.settings.effective_defaults.load_effective_profile", broken)

    assert default_research_provider().provider_name == "claude_cli"
    assert providers == [("default", None)]


def test_only_a_local_provider_is_told_not_to_think() -> None:
    assert model_route.no_thinking_options("lmstudio") == {"thinking": False}
    assert model_route.no_thinking_options("claude_cli") == {}  # hosted, though it could
    assert model_route.no_thinking_options("llamacpp") == {}  # local, but has no such option
    assert provider_supports("lmstudio", THINKING_OFF)


class _RecordingLMStudio(LMStudioProvider):
    def __init__(self) -> None:
        super().__init__(ProviderConfig(provider_type="lmstudio", base_url="http://127.0.0.1:1234", model="m"))
        self.payloads: list[dict] = []

    def _non_stream_completion(self, payload, **_):
        self.payloads.append(payload)
        return ChatResponse(content="{}", model="m")


def test_lm_studio_turns_thinking_off_only_when_asked() -> None:
    provider = _RecordingLMStudio()
    messages = [ChatMessage(role="user", content="?")]

    provider.chat_completion(messages, stream=False, thinking=False)
    provider.chat_completion(messages, stream=False)

    assert provider.payloads[0]["reasoning_effort"] == "none"
    assert "thinking" not in provider.payloads[0]
    assert "reasoning_effort" not in provider.payloads[1]


def test_lm_studio_native_chat_turns_reasoning_off_when_asked() -> None:
    provider = _RecordingLMStudio()

    payload = provider._native_v1_payload(
        [ChatMessage(role="user", content="?")],
        model="m", stream=False, store=False, previous_response_id=None, kwargs={"thinking": False},
    )

    assert payload["reasoning"] == "off"


class _Answer(BaseModel):
    ok: bool


class _LocalProvider:
    provider_name = "lmstudio"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat_completion(self, messages, **request):
        self.calls.append(request)
        return ChatResponse(content='{"ok": true}', model="m")


def test_a_research_call_to_a_local_model_sends_the_schema_and_no_thinking() -> None:
    assert sends_json_schema("lmstudio")  # LM Studio refuses response_format json_object
    provider = _LocalProvider()

    trading_model_call(
        provider, [ChatMessage(role="user", content="?")],
        output_model=_Answer, contract_id=SHADOW, schema_name="answer", model="m", max_tokens=50,
        budget=TradingAIBudget(backend=MemoryEvidenceBackend(), daily_calls=0),
    )

    assert provider.calls[0]["response_format"]["type"] == "json_schema"
    assert provider.calls[0]["thinking"] is False


def test_a_plain_research_call_to_a_local_model_does_not_think() -> None:
    provider = _LocalProvider()
    provider.chat_completion = lambda messages, **request: (provider.calls.append(request), ChatResponse(content="x", model="m"))[1]

    assert _call_provider(provider, [ChatMessage(role="user", content="?")], "m") == "x"
    assert provider.calls[0]["thinking"] is False


def _at() -> datetime:
    return datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)


def test_an_unmetered_budget_counts_and_refuses_nothing() -> None:
    backend = MemoryEvidenceBackend()
    budget = TradingAIBudget(backend=backend, daily_calls=1, clock=_at, unmetered=lambda: True)

    for _ in range(5):
        assert budget.can_acquire(SHADOW) is True
        budget.acquire(SHADOW)

    assert budget.status()["enabled"] is False
    assert budget.status()["counters"] == {}


def test_a_local_trading_provider_is_unmetered(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "lmstudio", "modelId": ""})
    assert model_route.trading_provider_is_local() is True

    _setting(monkeypatch, {"providerId": "claude_cli", "modelId": ""})
    assert model_route.trading_provider_is_local() is False

    assert default_trading_ai_budget()._unmetered is model_route.trading_provider_is_local


def test_the_budget_stays_on_when_locality_cannot_be_read(monkeypatch) -> None:
    from app.providers import service as provider_service

    def broken():
        raise RuntimeError("no provider")

    _setting(monkeypatch, None)
    monkeypatch.setattr(provider_service, "get_provider", broken)

    assert model_route.trading_provider_is_local() is False


def _row() -> dict:
    return {"instrument_id": "equity:NASDAQ:TEST", "observed_at": "2026-09-03T14:00:00+00:00", "feature_snapshot": {}}


class _RepairProvider:
    provider_name = "fixture"
    config = ProviderConfig(provider_type="fixture", model="fixture-ai")

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(content='{"decisions":[', usage=None, model="m")
        return SimpleNamespace(
            content=(
                '{"decisions":[{"instrument_id":"equity:NASDAQ:TEST","action":"skip","confidence":70,'
                '"market_regime":"unresolved","expected_horizon_minutes":30,"thesis":"x","reason":"y",'
                '"invalidation_price":null,"execution_authority":false}]}'
            ),
            usage=None,
            model="m",
        )


def test_the_repair_request_is_not_a_second_system_message() -> None:
    provider = _RepairProvider()

    AIShadowPolicyAnalyzer(provider_factory=lambda: provider).assess(policy="minute", rows=[_row()])

    roles = [message.role for message in provider.calls[1]["messages"]]
    assert roles.count("system") == 1 and roles[0] == "system"  # Qwen's template raises on a later system message
    assert "STRUCTURED OUTPUT REPAIR" in provider.calls[1]["messages"][-1].content


def test_the_task_says_what_confidence_means() -> None:
    task = _build_payload([_row()], policy="minute")["task"]

    assert "confidence is an integer from 1 to 100" in task
