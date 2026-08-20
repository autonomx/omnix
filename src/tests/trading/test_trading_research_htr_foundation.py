from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.trading.research.contracts import TradingEvidence, fingerprint
from app.trading.research.facts.metrics import derive_supply_metrics
from app.trading.research.facts.supply import extract_supply_facts
from app.trading.research.knowledge_time import latest_as_of


def _evidence(text: str, evidence_id: str = "e1") -> TradingEvidence:
    captured = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    return TradingEvidence(
        evidence_id=evidence_id, instrument_id="equity:NASDAQ:XYZ", evidence_type="sec_filing_content",
        source_type="sec", source_locator="https://sec.gov/test", source_authority_tier=1,
        source_published_at=captured, source_available_at=captured, captured_at=captured,
        omnix_known_at=captured, title="filing", content=text,
        content_hash="a" * 64, extraction_status="completed", metadata={},
        immutable_fingerprint=fingerprint({"id": evidence_id, "text": text}),
    )


def test_supply_parser_distinguishes_terminated_atm_from_active_atm():
    terminated = extract_supply_facts((_evidence("The previous at-the-market offering was terminated on August 10."),))
    active = extract_supply_facts((_evidence("The at-the-market offering remains available with $80 million remaining capacity."),))
    assert terminated[0].supply_type == "atm" and terminated[0].status == "terminated"
    assert active[0].status == "active" and active[0].remaining_capacity_usd == Decimal("80000000")


def test_supply_parser_distinguishes_exercised_and_exercisable_warrants():
    exercised = extract_supply_facts((_evidence("All outstanding warrants were exercised.", "e2"),))
    exercisable = extract_supply_facts((_evidence("10 million warrants are exercisable at an exercise price of $1.50.", "e3"),))
    assert exercised[0].status == "exhausted"
    assert exercisable[0].status == "exercisable"
    assert exercisable[0].shares == Decimal("10000000")
    assert exercisable[0].strike_price == Decimal("1.50")


def test_supply_metrics_are_continuous_not_keyword_vetoes():
    facts = extract_supply_facts((_evidence("10 million warrants are exercisable at an exercise price of $1.50."),))
    metrics = derive_supply_metrics(facts, float_shares=Decimal("8000000"), market_cap=Decimal("25000000"), market_price=Decimal("1.80"))
    assert metrics.in_the_money_warrant_pct_float == Decimal("125")
    assert metrics.immediate_supply_risk is True


def test_later_knowledge_is_not_visible_to_earlier_decision():
    first = _evidence("first", "early")
    later = _evidence("later", "late").model_copy(update={"omnix_known_at": first.omnix_known_at + timedelta(minutes=12)})
    assert latest_as_of([first, later], first.omnix_known_at + timedelta(minutes=6)).evidence_id == "early"
    assert latest_as_of([first, later], first.omnix_known_at + timedelta(minutes=13)).evidence_id == "late"


def test_research_package_has_no_order_execution_imports():
    root = Path(__file__).resolve().parents[2] / "app" / "trading" / "research"
    forbidden = ("paper_repository", "place_order", "execution_api", "paper_api")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), f"forbidden execution dependency in {path}"
