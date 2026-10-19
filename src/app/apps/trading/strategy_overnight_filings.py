"""SEC filings context for ``overnight-trading-strategy-shadow`` (research only).

For each population stock, what EDGAR showed by the decision time (filings accepted after it are
ignored, so the record is point-in-time even when it is fetched a little later):

- filings accepted today, with 8-K items (intraday catalysts);
- the latest earnings report (8-K item 2.02) and the *estimated* next one (52 weeks after its match);
- dilution signals: shelf registrations (S-3/F-3 family, 3 years), registrations (S-1/F-1/S-11
  family, 180 days) and prospectus filings (424B*, 90 days);
- insider open-market purchases (Form 4 transaction code P, 30 days, newest few parsed);
- Schedule 13D filings with the stock as subject (30 days).

No arm reads it; nothing here places, sizes or routes an order.
"""
from __future__ import annotations

import threading
import time as _time
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict

from .company_profiles import SecCompanySource
from .corporate_events import earnings_from_submissions, estimated_next_earnings, session_of
from .sec_contact import SecContactRequired

FILINGS_SOURCE = "sec_edgar"
SHELF_FORMS = frozenset({"S-3", "S-3/A", "S-3ASR", "F-3", "F-3/A", "F-3ASR"})
REGISTRATION_FORMS = frozenset({"S-1", "S-1/A", "F-1", "F-1/A", "S-11", "S-11/A"})
SCHEDULE_13D_FORMS = frozenset({"SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A"})
FORM4_FORMS = frozenset({"4", "4/A"})
SHELF_WINDOW = timedelta(days=3 * 365)
REGISTRATION_WINDOW = timedelta(days=180)
PROSPECTUS_WINDOW = timedelta(days=90)
INSIDER_WINDOW = timedelta(days=30)
SCHEDULE_13D_WINDOW = timedelta(days=30)
MAX_FORM4_PER_SYMBOL = 5
MAX_FORM4_BYTES = 2_000_000
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"


class OvernightFiling(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    form: str
    items: str | None
    accepted_at: datetime


class OvernightInsiderPurchases(BaseModel):
    """Open-market purchases (code P) in the newest ``parsed`` of ``forms`` Form 4 filings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    forms: int
    parsed: int
    purchases: int
    buyers: int
    shares: Decimal
    value: Decimal


class OvernightFilingContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    cik: str | None
    filings_today: list[OvernightFiling] = []
    last_earnings: date | None = None
    next_earnings_estimate: date | None = None
    shelf_last: date | None = None
    registration_last: date | None = None
    prospectus_count: int = 0
    prospectus_last: date | None = None
    schedule_13d_count: int = 0
    insider: OvernightInsiderPurchases | None = None
    error: str | None = None


def _accepted(raw: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def known_by(submissions: dict[str, Any], decided_at: datetime) -> dict[str, Any]:
    """``submissions`` with only the recent filings accepted by ``decided_at``."""

    recent = (submissions.get("filings") or {}).get("recent") or {}
    accepted = [_accepted(raw) for raw in recent.get("acceptanceDateTime") or []]
    keep = [index for index, moment in enumerate(accepted) if moment is not None and moment <= decided_at]
    filtered = {
        key: [values[index] for index in keep if index < len(values)]
        for key, values in recent.items() if isinstance(values, list)
    }
    return {**submissions, "filings": {"recent": filtered}}


def _filings(submissions: dict[str, Any]) -> list[tuple[str, str | None, datetime, str, str]]:
    """``(form, items, accepted_at, accession, primary_document)`` of the recent filings."""

    recent = (submissions.get("filings") or {}).get("recent") or {}
    rows = []
    for index, form in enumerate(recent.get("form") or []):
        try:
            accepted = _accepted(recent["acceptanceDateTime"][index])
            items = recent.get("items", [None] * (index + 1))[index] or None
            accession = str(recent["accessionNumber"][index])
            document = str(recent.get("primaryDocument", [""] * (index + 1))[index] or "")
        except (KeyError, IndexError):
            continue
        if accepted is not None:
            rows.append((str(form), items, accepted, accession, document))
    return rows


def form4_purchases(document: bytes) -> tuple[set[str], list[tuple[Decimal, Decimal]]]:
    """Reporting owners and open-market purchases ``(shares, price)`` of one Form 4 XML document."""

    root = ElementTree.fromstring(document)
    owners = {
        (node.text or "").strip()
        for node in root.iter("rptOwnerCik") if (node.text or "").strip()
    }
    purchases = []
    for transaction in root.iter("nonDerivativeTransaction"):
        if (transaction.findtext("transactionCoding/transactionCode") or "").strip() != "P":
            continue
        try:
            shares = Decimal((transaction.findtext("transactionAmounts/transactionShares/value") or "0").strip())
            price = Decimal((transaction.findtext("transactionAmounts/transactionPricePerShare/value") or "0").strip())
        except InvalidOperation:
            continue
        purchases.append((shares, price))
    return owners, purchases


def filing_context(
    symbol: str,
    cik: str,
    submissions: dict[str, Any],
    *,
    decided_at: datetime,
    form4_documents: Sequence[bytes] | None = None,
) -> OvernightFilingContext:
    """The context from ``submissions`` already cut to ``decided_at`` (see :func:`known_by`).

    ``form4_documents`` are the newest Form 4 XML documents inside the insider window (None: not fetched).
    """

    day = session_of(decided_at)[0]
    rows = _filings(submissions)
    earnings = earnings_from_submissions(submissions)
    estimate = estimated_next_earnings(earnings, day, submissions.get("fiscalYearEnd"))

    def latest(forms: frozenset[str] | None, window: timedelta, prefix: str = "") -> list[datetime]:
        return [
            accepted for form, _items, accepted, _a, _d in rows
            if (form in forms if forms else form.startswith(prefix)) and decided_at - accepted <= window
        ]

    shelves = latest(SHELF_FORMS, SHELF_WINDOW)
    registrations = latest(REGISTRATION_FORMS, REGISTRATION_WINDOW)
    prospectuses = latest(None, PROSPECTUS_WINDOW, prefix="424B")
    insider = None
    if form4_documents is not None:
        owners: set[str] = set()
        purchases: list[tuple[Decimal, Decimal]] = []
        parsed = 0
        for document in form4_documents:
            try:
                found_owners, found = form4_purchases(document)
            except ElementTree.ParseError:
                continue
            parsed += 1
            purchases += found
            if found:
                owners |= found_owners
        insider = OvernightInsiderPurchases(
            forms=len(latest(FORM4_FORMS, INSIDER_WINDOW)), parsed=parsed, purchases=len(purchases),
            buyers=len(owners), shares=sum((s for s, _ in purchases), Decimal("0")),
            value=sum((s * p for s, p in purchases), Decimal("0")),
        )
    return OvernightFilingContext(
        symbol=symbol,
        cik=cik,
        filings_today=[
            OvernightFiling(form=form, items=items, accepted_at=accepted)
            for form, items, accepted, _a, _d in rows if session_of(accepted)[0] == day
        ],
        last_earnings=max((e.date for e in earnings), default=None),
        next_earnings_estimate=estimate.date if estimate else None,
        shelf_last=session_of(max(shelves))[0] if shelves else None,
        registration_last=session_of(max(registrations))[0] if registrations else None,
        prospectus_count=len(prospectuses),
        prospectus_last=session_of(max(prospectuses))[0] if prospectuses else None,
        schedule_13d_count=len(latest(SCHEDULE_13D_FORMS, SCHEDULE_13D_WINDOW)),
        insider=insider,
    )


def form4_urls(cik: str, submissions: dict[str, Any], decided_at: datetime) -> list[str]:
    """Raw XML of the newest Form 4 filings inside the insider window (the styled copy's folder dropped)."""

    rows = sorted(
        (
            (accepted, accession, document) for form, _i, accepted, accession, document in _filings(submissions)
            if form in FORM4_FORMS and document and decided_at - accepted <= INSIDER_WINDOW
        ),
        reverse=True,
    )[:MAX_FORM4_PER_SYMBOL]
    return [
        _ARCHIVES.format(cik=int(cik), accession=accession.replace("-", ""), document=document.rsplit("/", 1)[-1])
        for _accepted_at, accession, document in rows
    ]


class OvernightFilingsSource:
    """EDGAR reads within the ``sec_edgar`` request budget, stopping at a time budget."""

    _directory: tuple[date, dict[str, tuple[str, str]]] | None = None
    _directory_lock = threading.Lock()

    def __init__(self, sec: SecCompanySource | None = None, *, clock: Callable[[], float] = _time.monotonic) -> None:
        self.sec = sec or SecCompanySource()
        self.clock = clock

    def _tickers(self, day: date) -> dict[str, tuple[str, str]]:
        cls = type(self)
        with cls._directory_lock:
            if cls._directory is None or cls._directory[0] != day:
                cls._directory = (day, self.sec.tickers())
            return cls._directory[1]

    def _bytes(self, url: str) -> bytes:
        response = self.sec.runtime.get(url, headers=self.sec.headers(), timeout=30)
        content = response.content
        if len(content) > MAX_FORM4_BYTES:
            raise ValueError("form 4 document too large")
        return content

    def contexts(
        self, symbols: Sequence[str], *, decided_at: datetime, budget_seconds: float = 120.0,
    ) -> tuple[list[OvernightFilingContext], bool]:
        """Contexts for ``symbols`` and whether the time budget cut the list short.

        A missing contact email (``SecContactRequired``) or ticker directory raises; a failure for
        one company is recorded on its context.
        """

        started = self.clock()
        directory = self._tickers(session_of(decided_at)[0])
        contexts: list[OvernightFilingContext] = []
        for symbol in symbols:
            if self.clock() - started > budget_seconds:
                return contexts, True
            entry = directory.get(symbol.replace(".", "-")) or directory.get(symbol)
            if entry is None:
                contexts.append(OvernightFilingContext(symbol=symbol, cik=None))
                continue
            cik = entry[0]
            try:
                submissions = known_by(self.sec.submissions(cik), decided_at)
                documents = []
                for url in form4_urls(cik, submissions, decided_at):
                    if self.clock() - started > budget_seconds:
                        break
                    documents.append(self._bytes(url))
                contexts.append(filing_context(symbol, cik, submissions, decided_at=decided_at,
                                               form4_documents=documents))
            except SecContactRequired:
                raise
            except Exception as exc:
                contexts.append(OvernightFilingContext(symbol=symbol, cik=cik, error=f"{type(exc).__name__}: {exc}"))
        return contexts, False


__all__ = [
    "FILINGS_SOURCE",
    "OvernightFiling",
    "OvernightFilingContext",
    "OvernightFilingsSource",
    "OvernightInsiderPurchases",
    "filing_context",
    "form4_purchases",
    "form4_urls",
    "known_by",
]
