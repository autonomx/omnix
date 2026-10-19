from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.apps.trading.sec_contact import SecContactRequired
from app.apps.trading.strategy_overnight_filings import (
    OvernightFilingsSource,
    filing_context,
    form4_purchases,
    form4_urls,
    known_by,
)

D = Decimal
DECIDED = datetime(2026, 10, 13, 19, 50, tzinfo=timezone.utc)   # 15:50 ET


def _submissions(*rows):
    """rows: (form, accepted ISO, items, accession, document)."""
    return {
        "cik": "123", "fiscalYearEnd": "1231",
        "filings": {"recent": {
            "form": [r[0] for r in rows],
            "acceptanceDateTime": [r[1] for r in rows],
            "items": [r[2] for r in rows],
            "accessionNumber": [r[3] for r in rows],
            "primaryDocument": [r[4] for r in rows],
        }},
    }


SUBMISSIONS = _submissions(
    ("8-K", "2026-10-13T20:30:00.000Z", "1.01", "0001-26-000009", "after.htm"),       # after the decision: unseen
    ("8-K", "2026-10-13T14:05:00.000Z", "8.01", "0001-26-000008", "today.htm"),       # 10:05 ET today
    ("4", "2026-10-10T21:00:00.000Z", None, "0001-26-000007", "xslF345X06/ownership.xml"),
    ("4", "2026-08-01T21:00:00.000Z", None, "0001-26-000006", "xslF345X06/old.xml"),  # outside 30 days
    ("SCHEDULE 13D", "2026-10-01T12:00:00.000Z", None, "0001-26-000005", "d.htm"),
    ("424B5", "2026-09-01T12:00:00.000Z", None, "0001-26-000004", "p.htm"),
    ("424B3", "2026-05-01T12:00:00.000Z", None, "0001-26-000003", "q.htm"),            # outside 90 days
    ("S-3", "2024-06-03T12:00:00.000Z", None, "0001-24-000002", "s3.htm"),
    ("8-K", "2025-10-14T20:10:00.000Z", "2.02,9.01", "0001-25-000001", "e.htm"),      # earnings a year ago
    ("8-K", "2026-08-12T20:10:00.000Z", "2.02", "0001-26-000000", "e2.htm"),          # latest earnings
)

FORM4 = b"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0000999</rptOwnerCik></reportingOwnerId></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>2.50</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>3</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_known_by_drops_filings_accepted_after_the_decision() -> None:
    cut = known_by(SUBMISSIONS, DECIDED)
    assert "0001-26-000009" not in cut["filings"]["recent"]["accessionNumber"]
    assert len(cut["filings"]["recent"]["form"]) == 9 and cut["fiscalYearEnd"] == "1231"


def test_filing_context_features_are_point_in_time() -> None:
    cut = known_by(SUBMISSIONS, DECIDED)
    c = filing_context("ABC", "0000000123", cut, decided_at=DECIDED, form4_documents=[FORM4, b"<broken"])
    assert [(f.form, f.items) for f in c.filings_today] == [("8-K", "8.01")]
    assert c.last_earnings == date(2026, 8, 12)
    assert c.next_earnings_estimate == date(2026, 10, 13)          # 52 weeks after 2025-10-14
    assert c.shelf_last == date(2024, 6, 3) and c.registration_last is None
    assert c.prospectus_count == 1 and c.prospectus_last == date(2026, 9, 1)
    assert c.schedule_13d_count == 1
    assert c.insider is not None
    assert (c.insider.forms, c.insider.parsed, c.insider.purchases, c.insider.buyers) == (1, 1, 1, 1)
    assert c.insider.shares == D("1000") and c.insider.value == D("2500.00")
    unfetched = filing_context("ABC", "0000000123", cut, decided_at=DECIDED)
    assert unfetched.insider is None


def test_form4_parsing_and_urls() -> None:
    owners, purchases = form4_purchases(FORM4)
    assert owners == {"0000999"} and purchases == [(D("1000"), D("2.50"))]
    assert form4_urls("0000000123", known_by(SUBMISSIONS, DECIDED), DECIDED) == [
        "https://www.sec.gov/Archives/edgar/data/123/000126000007/ownership.xml"]


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content


class FakeSec:
    def __init__(self, *, fail_for=(), contact=True) -> None:
        self.fail_for = set(fail_for)
        self.contact = contact
        self.runtime = self
        self.requests = []

    def headers(self):
        if not self.contact:
            raise SecContactRequired()
        return {}

    def tickers(self):
        self.headers()
        return {"ABC": ("0000000123", "Abc"), "BAD": ("0000000456", "Bad"), "BRK-B": ("0000000789", "Brk")}

    def submissions(self, cik):
        self.requests.append(cik)
        if cik in self.fail_for:
            raise RuntimeError("submissions failed")
        return SUBMISSIONS

    def get(self, url, **kwargs):
        self.requests.append(url)
        return FakeResponse(FORM4)


def test_source_records_per_company_failures_missing_filers_and_dotted_tickers() -> None:
    OvernightFilingsSource._directory = None
    sec = FakeSec(fail_for={"0000000456"})
    contexts, truncated = OvernightFilingsSource(sec).contexts(["ABC", "BAD", "NONE", "BRK.B"], decided_at=DECIDED)
    assert truncated is False
    by = {c.symbol: c for c in contexts}
    assert by["ABC"].insider is not None and by["ABC"].insider.purchases == 1 and by["ABC"].error is None
    assert by["BAD"].error == "RuntimeError: submissions failed"
    assert by["NONE"].cik is None and by["NONE"].error is None       # not an SEC filer
    assert by["BRK.B"].cik == "0000000789"


def test_source_stops_at_the_time_budget_and_raises_without_a_contact() -> None:
    OvernightFilingsSource._directory = None
    ticks = iter([0.0, 0.0, 0.0, 500.0, 500.0, 500.0])
    contexts, truncated = OvernightFilingsSource(FakeSec(), clock=lambda: next(ticks)).contexts(
        ["ABC", "ABC2", "ABC3"], decided_at=DECIDED, budget_seconds=120)
    assert truncated is True and [c.symbol for c in contexts] == ["ABC"]
    OvernightFilingsSource._directory = None
    with pytest.raises(SecContactRequired):
        OvernightFilingsSource(FakeSec(contact=False)).contexts(["ABC"], decided_at=DECIDED)
