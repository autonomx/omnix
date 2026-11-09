"""What a local model is asked for and what happens when part of its answer is unusable."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.apps.trading import model_route, strategy_ai_shadow_provider as lane
from app.apps.trading.local_batch import local_batch_call, per_instrument_format
from app.apps.trading.strategy_ai_shadow_v2 import AIShadowV2AlphaDecision, AIShadowV2Analyzer
from app.apps.trading.strategy_ai_shadow_v3 import AIShadowV3Analyzer, AIShadowV3Decision
from app.apps.trading.strategy_local_model_monitor import TradingLocalModelMonitor, create_trading_local_model_monitor_task
from app.apps.trading.structured_llm import TradingModelOutputError, trading_model_call
from app.apps.trading.trading_ai_budget import TradingAIBudget
from app.apps.trading.evidence_storage import MemoryEvidenceBackend
from app.providers import ChatMessage
from app.providers.base import ChatResponse, ConnectionError as ProviderConnectionError, ProviderConfig
from app.providers.lmstudio_provider import LMStudioProvider

V2_REQUIRES = {"armed": ("trigger",), "enter": ("invalidation_price", "target_1")}
IDS = ["equity:US:AAA", "equity:US:BBB", "equity:US:CCC"]
TRIGGER = {"trigger_type": "new_session_high", "price": 11.0, "min_volume_ratio": None, "expiry_minutes": 30}


def _v2(instrument_id: str, state: str = "watch", **extra) -> dict:
    return {
        "instrument_id": instrument_id, "setup_family": "unresolved", "state": state, "quality_score": 50,
        "entry_zone_low": None, "entry_zone_high": None, "invalidation_price": None, "target_1": None, "target_2": None,
        "trigger": None, "extension_risk": "medium", "evidence_for": [], "evidence_against": [], "thesis_changed": False,
        "thesis": "x", "execution_authority": False, **extra,
    }


class _Local:
    provider_name = "lmstudio"
    config = ProviderConfig(provider_type="lmstudio", model="m")

    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def chat_completion(self, messages, **request):
        self.calls.append({"messages": messages, **request})
        reply = self.replies.pop(0)
        if isinstance(reply, ChatResponse):
            return reply
        return ChatResponse(content=json.dumps({"decisions": reply}), model="served", finish_reason="stop")

    def requested_ids(self, index: int) -> list[str]:
        return [row["instrument_id"] for row in json.loads(self.calls[index]["messages"][-1].content)]


def _call(provider, rows=None):
    return local_batch_call(
        provider,
        rows=rows or [{"instrument_id": instrument_id} for instrument_id in IDS],
        build_messages=lambda batch: [ChatMessage(role="user", content=json.dumps(batch))],
        item_model=AIShadowV2AlphaDecision,
        requires=V2_REQUIRES,
        contract_id="trading.test",
        schema_name="test",
        model="m",
        max_tokens=lambda count: 100 * count,
    )


def test_the_schema_names_every_stock_in_order_exactly_once() -> None:
    schema = per_instrument_format(AIShadowV2AlphaDecision, IDS, requires=V2_REQUIRES, schema_name="s")["json_schema"]["schema"]
    decisions = schema["properties"]["decisions"]

    assert decisions["minItems"] == decisions["maxItems"] == 3
    assert [slot["anyOf"][0]["properties"]["instrument_id"]["const"] for slot in decisions["prefixItems"]] == IDS


def test_the_schema_requires_what_each_state_needs() -> None:
    schema = per_instrument_format(AIShadowV2AlphaDecision, IDS[:1], requires=V2_REQUIRES, schema_name="s")["json_schema"]["schema"]
    free, armed, enter = schema["properties"]["decisions"]["prefixItems"][0]["anyOf"]

    assert "armed" not in free["properties"]["state"]["enum"] and "enter" not in free["properties"]["state"]["enum"]
    assert armed["properties"]["state"] == {"const": "armed"} and "$ref" in armed["properties"]["trigger"]
    assert enter["properties"]["invalidation_price"]["type"] == "number"
    assert enter["properties"]["target_1"]["type"] == "number"
    assert armed["properties"]["thesis"]["maxLength"] == 400
    assert armed["properties"]["evidence_for"]["maxItems"] == 3
    assert set(armed["required"]) >= {"instrument_id", "state", "trigger", "thesis"}


def test_a_stock_left_out_costs_only_itself_and_is_asked_once_more() -> None:
    provider = _Local([_v2(IDS[0]), _v2(IDS[1])], [_v2(IDS[2])])

    batch = _call(provider)

    assert [item.instrument_id for item in batch.items] == IDS
    assert provider.requested_ids(1) == [IDS[2]]
    assert batch.unresolved == () and batch.attempts == 2


def test_a_stock_still_unanswered_stays_undecided_and_the_rest_are_kept() -> None:
    provider = _Local([_v2(IDS[0]), _v2(IDS[1])], [])

    batch = _call(provider)

    assert [item.instrument_id for item in batch.items] == IDS[:2]
    assert batch.unresolved == (IDS[2],)
    assert len(provider.calls) == 2


def test_armed_without_a_trigger_is_only_a_watch() -> None:
    provider = _Local([_v2(IDS[0], "armed"), _v2(IDS[1], "armed", trigger=TRIGGER), _v2(IDS[2], "enter")])

    batch = _call(provider)

    assert [item.state for item in batch.items] == ["watch", "armed", "watch"]
    assert batch.downgraded == (IDS[0], IDS[2])
    assert batch.attempts == 1


def test_an_unusable_decision_is_retried_alone() -> None:
    provider = _Local(
        [_v2(IDS[0]), _v2(IDS[1], entry_zone_low=10.0, entry_zone_high=9.0), _v2(IDS[2])],
        [_v2(IDS[1])],
    )

    batch = _call(provider)

    assert provider.requested_ids(1) == [IDS[1]]
    assert len(batch.items) == 3


def test_a_cut_off_reply_is_asked_again() -> None:
    cut_off = ChatResponse(content='{"decisions":[', model="m", finish_reason="length")
    provider = _Local(cut_off, [_v2(IDS[0]), _v2(IDS[1]), _v2(IDS[2])])

    assert len(_call(provider).items) == 3


def test_two_unusable_replies_raise_so_the_arm_records_an_error() -> None:
    cut_off = ChatResponse(content='{"decisions":[', model="m", finish_reason="length")

    with pytest.raises(TradingModelOutputError):
        _call(_Local(cut_off, cut_off))


def _alpha_rows() -> list[dict]:
    return [{"instrument_id": instrument_id, "feature_snapshot": {}} for instrument_id in IDS]


def test_v2_on_a_local_model_returns_what_it_could_decide(monkeypatch) -> None:
    provider = _Local([_v2(IDS[0]), _v2(IDS[1])], [])
    monkeypatch.setenv("OMNIX_TRADING_AI_DAILY_CALL_BUDGET", "0")

    decisions = AIShadowV2Analyzer(provider_factory=lambda: provider)._assess_core(arm="morning_control", rows=_alpha_rows())

    assert [item.instrument_id for item in decisions] == IDS[:2]
    assert provider.calls[0]["response_format"]["json_schema"]["schema"]["properties"]["decisions"]["minItems"] == 3


def _v3(instrument_id: str) -> dict:
    return {
        "instrument_id": instrument_id, "setup_family": "unresolved", "state": "watch", "quality_score": 40, "trigger": None,
        "geometry_suggestion": None, "evidence_for": [], "evidence_against": [], "thesis": "x", "execution_authority": False,
    }


def test_v3_on_a_local_model_keeps_the_rest_when_a_stock_is_left_out(monkeypatch) -> None:
    provider = _Local([_v3(IDS[0]), _v3(IDS[2])], [_v3(IDS[1])])
    monkeypatch.setenv("OMNIX_TRADING_AI_DAILY_CALL_BUDGET", "0")

    result = AIShadowV3Analyzer(provider_factory=lambda: provider).assess(_alpha_rows())

    assert {item.instrument_id for item in result.decisions} == set(IDS)
    assert isinstance(result.decisions[0], AIShadowV3Decision) and result.provider_latency_ms >= Decimal("0")


def test_a_local_model_gets_twice_the_output_limit() -> None:
    from pydantic import BaseModel

    class Answer(BaseModel):
        ok: bool

    budget = TradingAIBudget(backend=MemoryEvidenceBackend(), daily_calls=0)
    local = SimpleNamespace(provider_name="lmstudio", calls=[])
    hosted = SimpleNamespace(provider_name="claude_cli", calls=[])
    for provider in (local, hosted):
        provider.chat_completion = (
            lambda target: lambda messages, **request: (target.calls.append(request), ChatResponse(content='{"ok": true}', model="m"))[1]
        )(provider)
        trading_model_call(
            provider, [ChatMessage(role="user", content="?")], output_model=Answer, contract_id="c", schema_name="s", model="m",
            max_tokens=500, budget=budget,
        )

    assert local.calls[0]["max_tokens"] == 1000 and hosted.calls[0]["max_tokens"] == 500


TOO_LONG = ProviderConnectionError(
    'HTTP error 400: 400 Bad Request; response_body={"error":"request (21041 tokens) exceeds the available context size"}'
)
NOT_LOADED = ProviderConnectionError('HTTP error 400: 400 Bad Request; response_body={"error":"Failed to load model"}')


def test_a_rejected_prompt_is_not_an_outage() -> None:
    assert lane._transport_failure(TOO_LONG) is False


def test_a_model_that_cannot_load_is_an_outage() -> None:
    assert lane._transport_failure(NOT_LOADED) is True


def test_a_rejected_prompt_fails_its_own_call_and_leaves_the_breaker_shut(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_TRADING_AI_SHADOW_CIRCUIT_PERSISTENCE", "0")
    lane.reset_ai_shadow_reliability_state()

    def raises(_analyzer, *, arm, rows):
        raise TOO_LONG

    analyzer = SimpleNamespace(provider_factory=None)
    with pytest.raises(ProviderConnectionError):
        lane.assess_ai_shadow_v2_with_shared_circuit(analyzer, arm="morning_control", rows=[], original=raises)

    assert lane._CIRCUIT.failure_count == 0
    lane.reset_ai_shadow_reliability_state()


class _Listing:
    def __init__(self, payload) -> None:
        self.payload = payload

    def json(self):
        return self.payload

    def close(self) -> None:
        pass


def test_lm_studio_reports_the_loaded_models_context() -> None:
    provider = LMStudioProvider(ProviderConfig(provider_type="lmstudio", base_url="http://127.0.0.1:1234", model="m"))
    provider._make_request = lambda *a, **k: _Listing({"models": [
        {"type": "llm", "key": "qwen", "loaded_instances": [{"id": "qwen", "config": {"context_length": 35584}}]},
    ]})

    assert provider.loaded_model() == ("qwen", 35584)


def _setting(monkeypatch, row) -> None:
    overrides = {} if row is None else {model_route.TRADING_ROUTE_KEY: row}
    profile = SimpleNamespace(global_settings=SimpleNamespace(routing=SimpleNamespace(task_overrides=overrides)))
    monkeypatch.setattr("app.settings.effective_defaults.load_effective_profile", lambda: profile)


def _routed(monkeypatch, loaded) -> None:
    from app.providers import service as provider_service

    def routed(name, model):
        return SimpleNamespace(
            provider_name=name, loaded_model=lambda: loaded, loaded_model_key=lambda: loaded[0] if loaded else None,
        )

    monkeypatch.setattr(provider_service, "get_routed_provider", routed)


@pytest.mark.parametrize(
    ("pinned", "loaded", "ready", "problems"),
    [
        ("", ("qwen", 35584), True, ()),
        ("qwen", ("qwen", 35584), True, ()),
        ("qwen", ("gemma", 35584), False, ("WRONG_MODEL_LOADED",)),
        ("", ("gemma", 8192), False, ("CONTEXT_TOO_SMALL",)),
        ("", None, False, ("NO_MODEL_LOADED",)),
    ],
)
def test_readiness(monkeypatch, pinned, loaded, ready, problems) -> None:
    _setting(monkeypatch, {"providerId": "lmstudio", "modelId": pinned})
    _routed(monkeypatch, loaded)

    status = model_route.local_model_readiness()

    assert (status.applicable, status.ready, status.problems) == (True, ready, problems)


def test_readiness_does_not_apply_to_a_hosted_provider(monkeypatch) -> None:
    _setting(monkeypatch, {"providerId": "claude_cli", "modelId": ""})
    from app.providers import service as provider_service

    monkeypatch.setattr(provider_service, "get_routed_provider", lambda name, model: SimpleNamespace(provider_name=name))

    assert model_route.local_model_readiness().applicable is False


def test_a_pinned_model_is_not_requested_while_another_is_loaded(monkeypatch) -> None:
    _setting(monkeypatch, {"providerId": "lmstudio", "modelId": "qwen"})
    _routed(monkeypatch, ("gemma", 35584))

    with pytest.raises(model_route.TradingLocalModelNotReady):
        model_route.trading_provider()


class _Events:
    def __init__(self) -> None:
        self.events = []

    def append_event(self, event) -> bool:
        self.events.append(event)
        return True


NOT_READY = model_route.LocalModelReadiness(applicable=True, ready=False, model="gemma", context_length=8192, problems=("CONTEXT_TOO_SMALL",))
READY = model_route.LocalModelReadiness(applicable=True, ready=True, model="qwen", context_length=35584)
MONDAY_9_ET = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)


def _monitor(statuses, now=MONDAY_9_ET):
    events = _Events()
    pending = list(statuses)
    return events, TradingLocalModelMonitor(strategy_repository_factory=lambda: events, readiness=lambda: pending.pop(0), now_factory=lambda: now)


def test_the_monitor_reports_only_when_the_answer_changes() -> None:
    events, monitor = _monitor([NOT_READY, NOT_READY, READY])

    for _ in range(3):
        asyncio.run(monitor.run_once())

    assert [event.state for event in events.events] == ["not_ready", "ready"]
    assert events.events[0].reason_code == "CONTEXT_TOO_SMALL"
    assert events.events[0].payload["execution_authority"] is False


@pytest.mark.parametrize(
    "now",
    [datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc), datetime(2026, 11, 9, 23, 0, tzinfo=timezone.utc), datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc)],
)
def test_the_monitor_is_quiet_outside_market_hours(now) -> None:
    events, monitor = _monitor([NOT_READY], now=now)

    assert asyncio.run(monitor.run_once()) == 0
    assert events.events == []


def test_the_monitor_registers_once() -> None:
    context = SimpleNamespace(runtime_state=SimpleNamespace())

    assert create_trading_local_model_monitor_task(context) is not None
    assert create_trading_local_model_monitor_task(context) is None
