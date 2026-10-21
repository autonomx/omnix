from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers import ConnectionError, ProviderConfig
from app.apps.trading import strategy_ai_shadow_provider as reliability
from app.apps.trading.strategy_ai_shadow import AIShadowPolicyAnalyzer


INSTRUMENT = "equity:NASDAQ:TEST"
VALID = (
    '{"decisions":[{"instrument_id":"equity:NASDAQ:TEST","action":"skip",'
    '"confidence":75,"market_regime":"unresolved","expected_horizon_minutes":30,'
    '"thesis":"No high-conviction setup.","reason":"Wait for stronger causal evidence.",'
    '"invalidation_price":null,"execution_authority":false}]}'
)


@pytest.fixture(autouse=True)
def isolate_reliability_state(monkeypatch):
    monkeypatch.setenv("OMNIX_TRADING_AI_SHADOW_CIRCUIT_PERSISTENCE", "0")
    reliability.reset_ai_shadow_reliability_state()
    reset_for_tests = getattr(reliability._CIRCUIT, "reset_for_tests", None)
    if callable(reset_for_tests):
        reset_for_tests()
    yield
    reliability.reset_ai_shadow_reliability_state()


def _row():
    return {
        "instrument_id": INSTRUMENT,
        "observed_at": "2026-09-03T14:00:00+00:00",
        "trigger_reasons": ["completed_1m_bar"],
        "feature_snapshot": {"market": {"current_price": "10"}},
        "previous_decision": None,
        "previous_feature_snapshot": None,
    }


class _Response:
    def __init__(self, content: str):
        self.content = content
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        self.model = "fixture-ai"


class SequenceProvider:
    provider_name = "fixture"
    config = ProviderConfig(provider_type="fixture", model="fixture-ai")

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.kwargs = []
        self.closed = False

    def chat_completion(self, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        if not self.outcomes:
            raise AssertionError("provider called more times than expected")
        value = self.outcomes.pop(0)
        if isinstance(value, BaseException):
            raise value
        return _Response(value)

    def close(self):
        self.closed = True


class LegacySignatureProvider:
    provider_name = "legacy-fixture"
    config = ProviderConfig(provider_type="fixture", model="fixture-ai")

    def __init__(self):
        self.calls = 0

    def chat_completion(self, messages, model=None, stream=False):
        del messages, model, stream
        self.calls += 1
        return _Response(VALID)


def test_invalid_json_gets_one_bounded_repair_retry():
    provider = SequenceProvider(['{"decisions":[', VALID])
    analyzer = AIShadowPolicyAnalyzer(provider_factory=lambda: provider)

    result = analyzer.assess(policy="minute", rows=[_row()])

    assert provider.calls == 2
    assert len(result.decisions) == 1
    assert result.decisions[0].instrument_id == INSTRUMENT
    assert result.total_tokens == 30
    repair_messages = provider.kwargs[1]["messages"]
    assert any(
        "STRUCTURED OUTPUT REPAIR" in message.content
        and "ai_shadow_output_truncated" in message.content
        for message in repair_messages
    )


def test_schema_failure_is_classified_and_repaired():
    invalid_schema = (
        '{"decisions":[{"instrument_id":"equity:NASDAQ:TEST","action":"dance",'
        '"confidence":75,"market_regime":"unresolved","expected_horizon_minutes":30,'
        '"thesis":"x","reason":"y","invalidation_price":null,'
        '"execution_authority":false}]}'
    )
    provider = SequenceProvider([invalid_schema, VALID])
    analyzer = AIShadowPolicyAnalyzer(provider_factory=lambda: provider)

    result = analyzer.assess(policy="event", rows=[_row()])

    assert provider.calls == 2
    assert result.decisions[0].action == "skip"
    assert "ai_shadow_output_schema_error" in provider.kwargs[1]["messages"][-1].content


def test_missing_decision_failure_reports_specific_final_class():
    provider = SequenceProvider([
        '{"decisions":[]}',
        '{"decisions":[]}',
    ])
    analyzer = AIShadowPolicyAnalyzer(provider_factory=lambda: provider)

    with pytest.raises(reliability.AIShadowReliabilityError) as exc_info:
        analyzer.assess(policy="event", rows=[_row()])

    text = str(exc_info.value)
    assert "ai_shadow_output_repair_exhausted" in text
    assert "initial=ai_shadow_output_missing_decisions" in text
    assert "final=ai_shadow_output_missing_decisions" in text
    assert provider.calls == 2


def test_internal_type_error_is_not_retried_as_signature_fallback():
    provider = SequenceProvider([TypeError("provider internal type failure")])
    analyzer = AIShadowPolicyAnalyzer(provider_factory=lambda: provider)

    with pytest.raises(TypeError, match="provider internal type failure"):
        analyzer.assess(policy="minute", rows=[_row()])

    assert provider.calls == 1


def test_legacy_provider_signature_is_selected_before_call():
    provider = LegacySignatureProvider()
    analyzer = AIShadowPolicyAnalyzer(provider_factory=lambda: provider)

    result = analyzer.assess(policy="minute", rows=[_row()])

    assert provider.calls == 1
    assert len(result.decisions) == 1
    assert result.decisions[0].instrument_id == INSTRUMENT


def test_dedicated_provider_lane_clones_foreground_provider(monkeypatch):
    foreground = SimpleNamespace(
        provider_name="fixture",
        config=ProviderConfig(provider_type="fixture", model="fixture-ai"),
    )
    replacement = SequenceProvider([VALID])

    class Registry:
        def __init__(self):
            self.calls = 0

        def create_provider(self, provider_name, provider_config):
            self.calls += 1
            assert provider_name == "fixture"
            assert provider_config is not foreground.config
            return replacement

    registry = Registry()
    monkeypatch.setattr(reliability, "get_provider", lambda: foreground)
    monkeypatch.setattr(reliability, "get_registry", lambda: registry)

    first = reliability.get_trading_research_provider()
    second = reliability.get_trading_research_provider()

    assert first is replacement
    assert second is replacement
    assert first is not foreground
    assert registry.calls == 1


def test_native_schema_is_used_on_dedicated_trading_lane(monkeypatch):
    provider = SequenceProvider([VALID])
    monkeypatch.setattr(
        reliability,
        "get_trading_research_provider",
        lambda: provider,
    )
    analyzer = AIShadowPolicyAnalyzer(
        provider_factory=reliability.get_trading_research_provider
    )

    result = analyzer.assess(policy="minute", rows=[_row()])

    assert len(result.decisions) == 1
    response_format = provider.kwargs[0]["response_format"]
    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "decisions" in schema["properties"]
    assert "$defs" in schema
    decision_schema = schema["$defs"]["AIShadowDecision"]
    assert decision_schema["additionalProperties"] is False
    assert set(decision_schema["required"]) == set(decision_schema["properties"])
    invalidation_schema = decision_schema["properties"]["invalidation_price"]
    assert all("pattern" not in branch for branch in invalidation_schema["anyOf"])


def test_30_minute_provider_outage_has_bounded_external_calls(monkeypatch):
    clock = [0.0]
    provider = SequenceProvider(
        [ConnectionError("HTTP 404 websocket outage")] * 20
    )
    monkeypatch.setattr(reliability.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        reliability,
        "get_trading_research_provider",
        lambda: provider,
    )
    analyzer = AIShadowPolicyAnalyzer(
        provider_factory=reliability.get_trading_research_provider
    )

    # Simulate one due AI-shadow evaluation per minute for 30 minutes. Each
    # half-open probe may perform one bounded transport recovery retry; the
    # 2m -> 5m -> 10m circuit prevents a request storm during the outage.
    for minute in range(30):
        clock[0] = float(minute * 60)
        with pytest.raises(reliability.AIShadowReliabilityError):
            analyzer.assess(policy="minute", rows=[_row()])

    assert provider.calls <= 10
    assert provider.calls < 30
    assert reliability._CIRCUIT.failure_count >= 3


class _QueuedLane:
    """The shared lane held by another research call for ``wait`` seconds."""

    def __init__(self, clock, *, wait: float, granted: bool = True):
        self.clock = clock
        self.wait = wait
        self.granted = granted
        self.inner = reliability.threading.RLock()
        self.timeouts = []

    def acquire(self, blocking=True, timeout=-1):
        if not self.timeouts:
            self.clock[0] += self.wait
        self.timeouts.append(timeout)
        return self.granted and self.inner.acquire()

    def release(self):
        self.inner.release()

    def __enter__(self):
        return self.inner.__enter__()

    def __exit__(self, *exc):
        return self.inner.__exit__(*exc)


def _dedicated_analyzer(monkeypatch, provider):
    monkeypatch.setattr(reliability, "get_trading_research_provider", lambda: provider)
    return AIShadowPolicyAnalyzer(provider_factory=reliability.get_trading_research_provider)


def test_time_queued_behind_the_lane_does_not_spend_the_call_budget(monkeypatch):
    # 2026-10-21: v1 waited ~58s behind v2/intraday calls, reached the provider
    # with under 5s left, made no call and still tripped the shared circuit.
    clock = [0.0]
    provider = SequenceProvider([VALID])
    monkeypatch.setattr(reliability.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(reliability, "_PROVIDER_LOCK", _QueuedLane(clock, wait=58.0))
    analyzer = _dedicated_analyzer(monkeypatch, provider)

    result = analyzer.assess(policy="minute", rows=[_row()])

    assert len(result.decisions) == 1
    assert provider.calls == 1
    assert (
        provider.kwargs[0]["request_timeout_seconds"]
        == reliability.AI_SHADOW_PRIMARY_ATTEMPT_SECONDS
    )
    assert reliability._CIRCUIT.failure_count == 0


def test_lane_that_stays_busy_skips_without_tripping_the_circuit(monkeypatch):
    clock = [0.0]
    provider = SequenceProvider([])
    lane = _QueuedLane(clock, wait=reliability.AI_SHADOW_LANE_WAIT_SECONDS, granted=False)
    monkeypatch.setattr(reliability.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(reliability, "_PROVIDER_LOCK", lane)
    analyzer = _dedicated_analyzer(monkeypatch, provider)

    with pytest.raises(reliability.AIShadowLaneUnavailable) as exc_info:
        analyzer.assess(policy="minute", rows=[_row()])

    assert exc_info.value.code == "ai_shadow_provider_lane_busy"
    assert lane.timeouts == [reliability.AI_SHADOW_LANE_WAIT_SECONDS]
    assert provider.calls == 0
    assert reliability._CIRCUIT.failure_count == 0


def test_open_circuit_is_reported_as_lane_unavailable(monkeypatch):
    provider = SequenceProvider([])
    analyzer = _dedicated_analyzer(monkeypatch, provider)
    reliability._CIRCUIT.trip(reliability.time.monotonic())

    with pytest.raises(reliability.AIShadowLaneUnavailable) as exc_info:
        analyzer.assess(policy="event", rows=[_row()])

    assert exc_info.value.code == "ai_shadow_provider_circuit_open"
    assert provider.calls == 0


def test_budget_spent_before_any_attempt_does_not_trip_the_circuit(monkeypatch):
    provider = SequenceProvider([])
    analyzer = _dedicated_analyzer(monkeypatch, provider)

    with pytest.raises(reliability.AIShadowReliabilityError) as exc_info:
        reliability._chat_call_unlocked(
            analyzer,
            messages=[],
            model=None,
            response_format={"type": "json_object"},
            max_tokens=900,
            deadline=reliability.time.monotonic() + 1.0,
        )

    assert not isinstance(exc_info.value, reliability.AIShadowLaneUnavailable)
    assert exc_info.value.code == "ai_shadow_call_budget_exhausted"
    assert provider.calls == 0
    assert reliability._CIRCUIT.failure_count == 0


def test_transport_recovery_retries_once_then_succeeds(monkeypatch):
    provider = SequenceProvider([
        ConnectionError("websocket disconnected"),
        VALID,
    ])
    monkeypatch.setattr(
        reliability,
        "get_trading_research_provider",
        lambda: provider,
    )
    analyzer = AIShadowPolicyAnalyzer(
        provider_factory=reliability.get_trading_research_provider
    )

    result = analyzer.assess(policy="event", rows=[_row()])

    assert provider.calls == 2
    assert len(result.decisions) == 1
    assert reliability._CIRCUIT.failure_count == 0
