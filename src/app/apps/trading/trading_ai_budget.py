"""Daily budget for trading research model calls (shared across processes).

Trading research analyzers call a model on every few strategy cycles; on busy
days they used the whole provider quota (on a subscription CLI: the user's own
session limit). The budget counts calls per Eastern-time day in the durable
evidence session counters, so every process and restart share one count, and
gives each tier its own cap as a share of the day's calls:

* ``live`` (the intraday LLM of AUTO PAPER strategies, read by live strategy
  passes): the whole budget, and the last 25% of the day is reserved for it;
* ``shadow`` (the intraday LLM of shadow strategies): 15%;
* ``research`` (AI shadow v2/v3 arms, and any analyzer not listed): 70%.

``shadow`` and ``research`` calls also stop when the day's total reaches the
live reserve. A call over its tier's cap raises ``TradingAIBudgetExhausted``
before any provider request; ``can_acquire`` lets a caller skip building a
request that would be refused. ``OMNIX_TRADING_AI_DAILY_CALL_BUDGET=0`` turns
the budget off. Research only: nothing here grants execution authority.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Literal

from app.config.env import environment

from .evidence_storage import default_evidence_backend
from .us_equity_calendar import EASTERN

Tier = Literal["live", "shadow", "research"]

AI_BUDGET_COUNTER_PROVIDER = "trading_ai_budget"
DEFAULT_DAILY_CALL_BUDGET = 400
INTRADAY_LLM_LIVE_CONTRACT = "trading.intraday_llm.batch"
INTRADAY_LLM_SHADOW_CONTRACT = "trading.intraday_llm.shadow_batch"
TIER_SHARE: dict[Tier, float] = {"live": 1.0, "shadow": 0.15, "research": 0.7}
# Share of the day only live calls may use.
LIVE_RESERVE_SHARE = 0.25
CONTRACT_TIERS: dict[str, Tier] = {
    INTRADAY_LLM_LIVE_CONTRACT: "live",
    INTRADAY_LLM_SHADOW_CONTRACT: "shadow",
    "trading.ai_shadow_v2.batch": "research",
    "trading.ai_shadow_v2.catalyst_semantics": "research",
    "trading.ai_shadow_v3.batch": "research",
}


class TradingAIBudgetExhausted(RuntimeError):
    """The day's cap for this call's tier is used up; no provider call was made."""

    def __init__(self, contract_id: str, tier: Tier, used: int, limit: int) -> None:
        super().__init__(
            f"trading_ai_budget_exhausted:{contract_id}:tier={tier};used={used};limit={limit}"
        )
        self.contract_id = contract_id
        self.tier = tier
        self.used = used
        self.limit = limit


# AI shadow research arms (v2/v3) ask the model at most once per clock-aligned
# slot of this many minutes, so every due name shares one call.
RESEARCH_DECISION_MINUTES = 5


def research_decision_slot(at: datetime) -> datetime:
    """Start (UTC) of the research decision slot containing ``at``."""

    value = at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return value - timedelta(minutes=value.minute % RESEARCH_DECISION_MINUTES)


def daily_call_budget() -> int:
    # The literal default keeps the generated configuration registry accurate.
    raw = environment().get("OMNIX_TRADING_AI_DAILY_CALL_BUDGET", "400").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_DAILY_CALL_BUDGET


def contract_tier(contract_id: str) -> Tier:
    return CONTRACT_TIERS.get(contract_id, "research")


def tier_limits(daily: int) -> dict[str, int]:
    """Each tier's cap, and the day's total only live calls may go past."""

    limits = {tier: math.floor(daily * share) for tier, share in TIER_SHARE.items()}
    limits["non_live_total"] = daily - math.floor(daily * LIVE_RESERVE_SHARE)
    return limits


def _refusal(counters: dict[str, int], daily: int, tier: Tier) -> tuple[int, int] | None:
    """(used, limit) of the cap a call of ``tier`` would exceed, or None."""

    limits = tier_limits(daily)
    total = int(counters.get("calls", 0))
    if tier == "live":
        return (total, daily) if total >= daily else None
    if total >= limits["non_live_total"]:
        return total, limits["non_live_total"]
    used = int(counters.get(f"calls:{tier}", 0))
    return (used, limits[tier]) if used >= limits[tier] else None


class TradingAIBudget:
    def __init__(
        self,
        *,
        backend: Any | None = None,
        daily_calls: int | Callable[[], int] = daily_call_budget,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._daily_calls = daily_calls
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Serializes check-and-count within a process; across processes the
        # overshoot is at most one call per concurrent caller.
        self._lock = Lock()

    @property
    def backend(self) -> Any:
        if self._backend is None:
            self._backend = default_evidence_backend()
        return self._backend

    def _limit(self) -> int:
        return self._daily_calls() if callable(self._daily_calls) else int(self._daily_calls)

    def _day(self):
        return self._clock().astimezone(EASTERN).date()

    def can_acquire(self, contract_id: str) -> bool:
        """Whether a call for ``contract_id`` would be allowed now; counts nothing."""

        daily = self._limit()
        if daily <= 0:
            return True
        counters, _ = self.backend.session_counters(AI_BUDGET_COUNTER_PROVIDER, self._day())
        return _refusal(counters, daily, contract_tier(contract_id)) is None

    def acquire(self, contract_id: str) -> None:
        """Count one call for ``contract_id`` or raise if its tier's cap is used up."""

        daily = self._limit()
        if daily <= 0:
            return
        tier = contract_tier(contract_id)
        day = self._day()
        with self._lock:
            counters, _ = self.backend.session_counters(AI_BUDGET_COUNTER_PROVIDER, day)
            refusal = _refusal(counters, daily, tier)
            if refusal is not None:
                self.backend.add_session_counters(AI_BUDGET_COUNTER_PROVIDER, day, {f"denied:{tier}": 1})
                raise TradingAIBudgetExhausted(contract_id, tier, *refusal)
            self.backend.add_session_counters(
                AI_BUDGET_COUNTER_PROVIDER, day, {"calls": 1, f"calls:{tier}": 1, f"calls:{contract_id}": 1}
            )

    def status(self) -> dict[str, Any]:
        daily = self._limit()
        counters, updated = self.backend.session_counters(AI_BUDGET_COUNTER_PROVIDER, self._day())
        return {
            "daily_call_budget": daily,
            "enabled": daily > 0,
            "tier_limits": tier_limits(daily),
            "counters": counters,
            "updated_at": updated.isoformat() if updated is not None else None,
        }


_default_budget: TradingAIBudget | None = None
_default_lock = Lock()


def default_trading_ai_budget() -> TradingAIBudget:
    global _default_budget
    if _default_budget is None:
        with _default_lock:
            if _default_budget is None:
                _default_budget = TradingAIBudget()
    return _default_budget


__all__ = [
    "AI_BUDGET_COUNTER_PROVIDER",
    "CONTRACT_TIERS",
    "DEFAULT_DAILY_CALL_BUDGET",
    "INTRADAY_LLM_LIVE_CONTRACT",
    "INTRADAY_LLM_SHADOW_CONTRACT",
    "LIVE_RESERVE_SHARE",
    "RESEARCH_DECISION_MINUTES",
    "TIER_SHARE",
    "TradingAIBudget",
    "TradingAIBudgetExhausted",
    "contract_tier",
    "daily_call_budget",
    "default_trading_ai_budget",
    "research_decision_slot",
    "tier_limits",
]
