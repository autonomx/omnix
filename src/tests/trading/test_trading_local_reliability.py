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


def test_force_flat_gives_the_exit_its_arms_feature_snapshot(monkeypatch) -> None:
    from datetime import time

    from app.apps.trading import strategy_ai_shadow_monitor as module

    monitor = module.TradingAIShadowMonitor(strategy_repository_factory=lambda: None, market_service_factory=lambda: None)
    captured: list[dict] = []

    async def capture(**kwargs):
        captured.append(kwargs["row"])

    monkeypatch.setattr(monitor, "_apply_decision", capture)
    monkeypatch.setattr(module, "_position_from_latest_fill", lambda *a, **k: SimpleNamespace(is_long=True))
    monkeypatch.setattr(module, "_pending_exit_intent", lambda *a, **k: None)
    row = {
        "candidate": SimpleNamespace(instrument_id=IDS[0]), "bars": [], "learning": None,
        "feature_by_policy": {"minute": {"policy": "minute"}, "event": {"policy": "event"}},
    }

    asyncio.run(
        monitor._force_flat_open_positions(
            rows=[row], config=SimpleNamespace(risk=SimpleNamespace(force_flat_et=time(15, 55))),
            repository=None, market_service=None, events=[],
            now=datetime(2026, 11, 6, 20, 56, tzinfo=timezone.utc),
        )
    )

    assert [item["feature_snapshot"]["policy"] for item in captured] == ["minute", "event"]


@pytest.fixture
def local_trading(monkeypatch):
    monkeypatch.setattr(model_route, "trading_provider_is_local", lambda: True)


def test_a_local_call_covers_five_stocks_open_ones_first(local_trading) -> None:
    rows = [{"name": f"S{index}", "open": index in {6, 7}} for index in range(9)]

    limited = model_route.local_batch_rows(rows, is_open=lambda row: row["open"])

    assert [row["name"] for row in limited] == ["S6", "S7", "S0", "S1", "S2"]


def test_more_than_five_open_stocks_still_stop_at_five(local_trading) -> None:
    rows = [{"name": f"S{index}", "open": True} for index in range(7)]

    assert len(model_route.local_batch_rows(rows, is_open=lambda row: row["open"])) == 5


def test_a_hosted_provider_is_not_capped(monkeypatch) -> None:
    monkeypatch.setattr(model_route, "trading_provider_is_local", lambda: False)
    rows = list(range(9))

    assert model_route.local_batch_rows(rows, is_open=lambda _: False) == rows


def test_a_second_local_call_waits_for_the_lane_and_gives_up_when_busy(monkeypatch) -> None:
    import threading

    monkeypatch.setattr(model_route, "LOCAL_LANE_WAIT_SECONDS", 0.01)
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with model_route.local_model_lane("lmstudio"):
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    try:
        with pytest.raises(model_route.TradingLocalLaneBusy):
            with model_route.local_model_lane("lmstudio"):
                pass
    finally:
        release.set()
        holder.join()


def test_a_hosted_provider_never_waits_for_the_lane() -> None:
    with model_route.LOCAL_MODEL_LANE:
        with model_route.local_model_lane("claude_cli"):
            pass


def _decision(at: datetime, state: str, stop) -> SimpleNamespace:
    return SimpleNamespace(
        event_type="ai_shadow_decision", instrument_id=IDS[0], state=state, observed_at=at, event_id=str(at),
        payload={"policy": "minute", "decision": {"action": state, "invalidation_price": stop}},
    )


def _ts(minute: int) -> datetime:
    return datetime(2026, 11, 9, 15, minute, tzinfo=timezone.utc)


def _long(entry_minute: int = 1) -> SimpleNamespace:
    return SimpleNamespace(is_long=True, entry_time=_ts(entry_minute))


def _stop(events, position=None):
    from app.apps.trading.strategy_ai_shadow_monitor import _model_stop_price

    return _model_stop_price(events, policy="minute", instrument_id=IDS[0], position=position or _long())


def test_the_model_can_raise_its_stop_but_not_lower_it() -> None:
    events = [_decision(_ts(0), "enter", "3.15"), _decision(_ts(5), "hold", "3.40"), _decision(_ts(9), "hold", "2.00")]

    assert _stop(events) == Decimal("3.40")


def test_an_earlier_trades_stop_does_not_carry_over() -> None:
    events = [
        _decision(_ts(0), "enter", "9.00"),
        _decision(_ts(2), "exit", None),
        _decision(_ts(10), "enter", "3.15"),
    ]

    assert _stop(events, _long(11)) == Decimal("3.15")


def test_no_stop_without_an_open_position_or_a_stated_price() -> None:
    assert _stop([_decision(_ts(0), "enter", None)]) is None
    assert _stop([_decision(_ts(0), "enter", "3")], SimpleNamespace(is_long=False, entry_time=None)) is None


def _policy_monitor(monkeypatch):
    from app.apps.trading import strategy_ai_shadow_monitor as module

    monitor = module.TradingAIShadowMonitor(strategy_repository_factory=lambda: None, market_service_factory=lambda: None)

    async def prepared(*, rows, **_):
        return rows

    monkeypatch.setattr(monitor, "_prepare_policy_rows", prepared)
    return module, monitor


def _risk():
    from datetime import time

    return SimpleNamespace(strategy_id="s", risk=SimpleNamespace(
        force_flat_et=time(15, 55), kill_switch=False, last_entry_et=time(11, 30), one_trade_per_symbol_per_day=False,
    ))


def test_a_close_through_the_models_stop_exits_without_asking_the_model(monkeypatch) -> None:
    module, monitor = _policy_monitor(monkeypatch)
    applied: list[dict] = []

    async def capture(**kwargs):
        applied.append(kwargs)

    def forbidden():
        raise AssertionError("the model must not be asked")

    monkeypatch.setattr(monitor, "_apply_decision", capture)
    monkeypatch.setattr(monitor, "analyzer_factory", forbidden)
    fill = SimpleNamespace(
        event_type="ai_shadow_fill", instrument_id=IDS[0], observed_at=_ts(1), event_id="f", state="filled",
        payload={"policy": "minute", "position_after": {
            "policy": "minute", "instrument_id": IDS[0], "normalized_units": "1", "entry_time": _ts(1).isoformat(),
        }},
    )
    row = {
        "candidate": SimpleNamespace(instrument_id=IDS[0]), "observed_at": _ts(30),
        "bars": [SimpleNamespace(close=Decimal("2.99"))], "learning": None, "universe_id": "u", "feature_snapshot": {},
    }

    asyncio.run(monitor._run_policy(
        policy="minute", rows=[row], config=_risk(), repository=None, market_service=None,
        events=[_decision(_ts(0), "enter", "3.15"), fill],
    ))

    assert applied[0]["decision"].action == "exit"
    assert applied[0]["trigger_reasons"] == ("model_stop_breached",)


def _flat_row(at: datetime) -> dict:
    return {
        "candidate": SimpleNamespace(instrument_id=IDS[0]), "observed_at": at,
        "bars": [SimpleNamespace(close=Decimal("5"))], "learning": None, "universe_id": "u", "feature_snapshot": {},
    }


def _earlier_decision(policy: str, at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        event_type="ai_shadow_decision", instrument_id=IDS[0], state="skip", observed_at=at, event_id=str(at),
        payload={"policy": policy, "decision": {"action": "skip", "invalidation_price": None}, "feature_snapshot": None},
    )


def _asked(monkeypatch, policy: str, row_at: datetime, earlier_at: datetime) -> int:
    module, monitor = _policy_monitor(monkeypatch)
    calls: list[str] = []

    class Stop(Exception):
        pass

    class Analyzer:
        def assess(self, *, policy, rows):
            calls.append(policy)
            raise Stop

    async def no_append(*_args, **_kwargs):
        return True

    monkeypatch.setattr(monitor, "analyzer_factory", Analyzer)
    monkeypatch.setattr(monitor, "_append", no_append)
    monkeypatch.setattr(module, "trade_log", lambda *a, **k: None)
    asyncio.run(monitor._run_policy(
        policy=policy, rows=[_flat_row(row_at)], config=_risk(), repository=None, market_service=None,
        events=[_earlier_decision(policy, earlier_at)],
    ))
    return len(calls)


@pytest.mark.parametrize("policy", ["minute", "event"])
def test_c_and_d_ask_the_model_once_per_five_minute_slot(monkeypatch, policy) -> None:
    assert _asked(monkeypatch, policy, row_at=_ts(33), earlier_at=_ts(31)) == 0
    assert _asked(monkeypatch, policy, row_at=_ts(35), earlier_at=_ts(31)) == 1


def test_the_stop_is_still_checked_inside_a_slot(monkeypatch) -> None:
    _module, monitor = _policy_monitor(monkeypatch)
    applied: list[dict] = []

    async def capture(**kwargs):
        applied.append(kwargs)

    monkeypatch.setattr(monitor, "_apply_decision", capture)
    fill = SimpleNamespace(
        event_type="ai_shadow_fill", instrument_id=IDS[0], observed_at=_ts(1), event_id="f", state="filled",
        payload={"policy": "minute", "position_after": {
            "policy": "minute", "instrument_id": IDS[0], "normalized_units": "1", "entry_time": _ts(1).isoformat(),
        }},
    )
    row = {**_flat_row(_ts(33)), "bars": [SimpleNamespace(close=Decimal("2.99"))]}

    asyncio.run(monitor._run_policy(
        policy="minute", rows=[row], config=_risk(), repository=None, market_service=None,
        events=[_decision(_ts(0), "enter", "3.15"), _decision(_ts(31), "hold", "3.15"), fill],
    ))

    assert applied[0]["trigger_reasons"] == ("model_stop_breached",)


def test_a_retry_looks_after_the_previous_attempt_not_the_refused_quote(monkeypatch) -> None:
    _module, monitor = _policy_monitor(monkeypatch)
    moments = iter([_ts(30), _ts(31), _ts(32), _ts(33)])
    monitor.now_factory = lambda: next(moments)
    original = _ts(10)

    assert monitor._retry_actionable_at("minute", IDS[0], original) == original
    assert monitor._retry_actionable_at("minute", IDS[0], original) == _ts(30)
    assert monitor._retry_actionable_at("minute", IDS[0], original) == _ts(31)
    assert monitor._retry_actionable_at("event", IDS[0], original) == original  # the other arm's order is its own


def test_c_and_d_send_the_open_position_inside_the_five(monkeypatch, local_trading) -> None:
    module, monitor = _policy_monitor(monkeypatch)
    sent: list[list[str]] = []

    class Stop(Exception):
        pass

    class Analyzer:
        def assess(self, *, policy, rows):
            sent.append([row["instrument_id"] for row in rows])
            raise Stop

    async def no_append(*_args, **_kwargs):
        return True

    monkeypatch.setattr(monitor, "analyzer_factory", Analyzer)
    monkeypatch.setattr(monitor, "_append", no_append)
    monkeypatch.setattr(module, "trade_log", lambda *a, **k: None)
    open_id = "equity:US:S7"
    fill = SimpleNamespace(
        event_type="ai_shadow_fill", instrument_id=open_id, observed_at=_ts(1), event_id="f", state="filled",
        payload={"policy": "minute", "position_after": {"policy": "minute", "instrument_id": open_id, "normalized_units": "1"}},
    )
    rows = [
        {
            "candidate": SimpleNamespace(instrument_id=f"equity:US:S{index}"), "observed_at": _ts(30),
            "bars": [SimpleNamespace(close=Decimal("5"))], "learning": None, "universe_id": "u", "feature_snapshot": {},
        }
        for index in range(9)
    ]

    asyncio.run(monitor._run_policy(
        policy="minute", rows=rows, config=_risk(), repository=None, market_service=None, events=[fill],
    ))

    assert sent[0][0] == open_id and len(sent[0]) == 5
