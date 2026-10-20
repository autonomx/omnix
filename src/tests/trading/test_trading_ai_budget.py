"""Trading research model calls: a daily budget with priority tiers, and schema-bound replies."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from app.apps.trading.evidence_storage import MemoryEvidenceBackend
from app.apps.trading.structured_llm import sends_json_schema, trading_model_call, trading_response_format
from app.apps.trading.trading_ai_budget import (
    AI_BUDGET_COUNTER_PROVIDER,
    INTRADAY_LLM_SHADOW_CONTRACT,
    TradingAIBudget,
    TradingAIBudgetExhausted,
    contract_tier,
    research_decision_slot,
    tier_limits,
)
from app.providers import ChatMessage
from app.providers.base import ChatResponse

INTRADAY = "trading.intraday_llm.batch"
SHADOW = "trading.ai_shadow_v3.batch"


def _budget(daily: int, clock=None) -> TradingAIBudget:
    now = clock or (lambda: datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc))
    return TradingAIBudget(backend=MemoryEvidenceBackend(), daily_calls=daily, clock=now)


def test_each_tier_has_its_own_cap_and_the_live_reserve_is_kept() -> None:
    assert (contract_tier(INTRADAY), contract_tier(INTRADAY_LLM_SHADOW_CONTRACT), contract_tier(SHADOW)) == (
        "live", "shadow", "research",
    )
    assert contract_tier("trading.unlisted.batch") == "research"
    assert tier_limits(20) == {"live": 20, "shadow": 3, "research": 14, "non_live_total": 15}
    budget = _budget(20)
    for _ in range(14):
        budget.acquire(SHADOW)  # research: its own 70%
    with pytest.raises(TradingAIBudgetExhausted) as research:
        budget.acquire(SHADOW)
    assert (research.value.tier, research.value.used, research.value.limit) == ("research", 14, 14)

    budget.acquire(INTRADAY_LLM_SHADOW_CONTRACT)  # shadow: under its 15%, but the day reaches the reserve
    assert budget.can_acquire(INTRADAY_LLM_SHADOW_CONTRACT) is False
    with pytest.raises(TradingAIBudgetExhausted) as shadow:
        budget.acquire(INTRADAY_LLM_SHADOW_CONTRACT)
    assert (shadow.value.tier, shadow.value.used, shadow.value.limit) == ("shadow", 15, 15)

    assert budget.can_acquire(INTRADAY) is True
    for _ in range(5):
        budget.acquire(INTRADAY)  # live: the reserved rest of the day
    assert budget.can_acquire(INTRADAY) is False
    with pytest.raises(TradingAIBudgetExhausted):
        budget.acquire(INTRADAY)
    counters = budget.status()["counters"]
    assert counters["calls"] == 20
    assert counters["calls:live"] == 5 and counters["calls:shadow"] == 1 and counters["calls:research"] == 14
    # can_acquire counts nothing; only refused acquire calls are recorded.
    assert counters["denied:research"] == 1 and counters["denied:shadow"] == 1 and counters["denied:live"] == 1


def test_a_shadow_tier_cap_applies_before_the_reserve() -> None:
    budget = _budget(20)
    for _ in range(3):
        budget.acquire(INTRADAY_LLM_SHADOW_CONTRACT)
    with pytest.raises(TradingAIBudgetExhausted) as shadow:
        budget.acquire(INTRADAY_LLM_SHADOW_CONTRACT)
    assert (shadow.value.used, shadow.value.limit) == (3, 3)
    budget.acquire(SHADOW)  # the research cap is separate


def test_research_decision_slots_are_clock_aligned_five_minutes() -> None:
    def at(hour: int, minute: int, second: int = 0) -> datetime:
        return datetime(2026, 10, 20, hour, minute, second, tzinfo=timezone.utc)

    assert research_decision_slot(at(13, 35)) == at(13, 35)
    assert research_decision_slot(at(13, 39, 59)) == at(13, 35)
    assert research_decision_slot(at(13, 40)) == at(13, 40)


def test_the_count_is_per_eastern_day_and_zero_turns_the_budget_off() -> None:
    now = [datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)]
    budget = _budget(2, clock=lambda: now[0])
    budget.acquire(INTRADAY)
    budget.acquire(INTRADAY)
    with pytest.raises(TradingAIBudgetExhausted):
        budget.acquire(INTRADAY)
    now[0] = datetime(2026, 10, 16, 4, 1, tzinfo=timezone.utc)  # 00:01 ET: a new day
    budget.acquire(INTRADAY)
    assert budget.backend.session_counters(AI_BUDGET_COUNTER_PROVIDER, now[0].date())[0]["calls"] == 1

    unlimited = _budget(0)
    for _ in range(50):
        unlimited.acquire(SHADOW)


class _Answer(BaseModel):
    ok: bool


class _Provider:
    provider_name = "claude_cli"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat_completion(self, messages, **request):
        self.calls.append(request)
        return ChatResponse(content='{"ok": true}', model="m")


def test_an_exhausted_budget_stops_the_call_before_the_provider() -> None:
    provider = _Provider()
    budget = _budget(1)
    messages = [ChatMessage(role="user", content="?")]
    call = dict(output_model=_Answer, contract_id=INTRADAY, schema_name="answer", model="m", max_tokens=50, budget=budget)

    assert trading_model_call(provider, messages, **call).value.ok is True
    with pytest.raises(TradingAIBudgetExhausted):
        trading_model_call(provider, messages, **call)
    assert len(provider.calls) == 1


def test_native_schema_providers_receive_the_output_schema() -> None:
    # Claude CLI enforces --json-schema; without it the model guessed the shape.
    assert sends_json_schema("claude_cli") and sends_json_schema("chatgpt_codex")
    assert not sends_json_schema("cerebras")
    assert not sends_json_schema("lmstudio")  # unchanged: a local model's schema support varies
    claude = trading_response_format(_Provider(), _Answer, "answer")
    assert claude["type"] == "json_schema" and claude["json_schema"]["schema"]["properties"]["ok"]
