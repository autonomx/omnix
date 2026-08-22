from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.trading.strategy_shadow_execution import observe_shadow_execution


INSTRUMENT = "equity:NASDAQ:SHADOW"
BINDING = "alpaca:iex:equity:NASDAQ:SHADOW"


def _execution(*, eligible: bool):
    return SimpleNamespace(
        instrument_id=INSTRUMENT,
        binding_id=BINDING,
        provider="alpaca_iex",
        last=Decimal("10.10"),
        bid=Decimal("10.09"),
        ask=Decimal("10.11"),
        bid_size=Decimal("500"),
        ask_size=Decimal("400"),
        high=Decimal("10.20"),
        low=Decimal("9.95"),
        bar_volume=Decimal("12000"),
        bar_start_time=datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc),
        source_time=datetime(2026, 8, 24, 14, 0, 30, tzinfo=timezone.utc),
        spread_bps=Decimal("19.80"),
        execution_eligible=eligible,
        freshness_mode="realtime",
        rejection_reasons=() if eligible else ("book_missing",),
        halted=False,
    )


class FakeMarketService:
    def __init__(self, execution) -> None:
        self.execution = execution
        self.calls: list[tuple[str, str | None]] = []

    def execution_observation(self, instrument_id: str, binding_id: str | None):
        self.calls.append((instrument_id, binding_id))
        return self.execution


def test_shadow_execution_captures_eligible_iex_evidence_without_order_authority() -> None:
    service = FakeMarketService(_execution(eligible=True))
    evidence = observe_shadow_execution(
        service,
        instrument_id=INSTRUMENT,
        binding_id=BINDING,
    )

    assert service.calls == [(INSTRUMENT, BINDING)]
    assert evidence.reason_code == "SHADOW_EXECUTION_OBSERVED"
    assert evidence.execution["execution_eligible"] is True
    assert evidence.execution["bid"] == Decimal("10.09")
    assert evidence.execution["ask"] == Decimal("10.11")
    assert evidence.execution["source_time"] == datetime(2026, 8, 24, 14, 0, 30, tzinfo=timezone.utc)


def test_shadow_execution_preserves_ineligible_reasons() -> None:
    service = FakeMarketService(_execution(eligible=False))
    evidence = observe_shadow_execution(
        service,
        instrument_id=INSTRUMENT,
        binding_id=BINDING,
    )

    assert evidence.reason_code == "SHADOW_EXECUTION_INELIGIBLE"
    assert evidence.execution["execution_eligible"] is False
    assert evidence.execution["rejection_reasons"] == ("book_missing",)


def test_shadow_execution_module_has_no_order_or_paper_repository_dependency() -> None:
    source = Path("src/app/trading/strategy_shadow_execution.py").read_text(encoding="utf-8")
    assert "paper_repository" not in source
    assert "place_order" not in source
    assert "PaperOrder" not in source
