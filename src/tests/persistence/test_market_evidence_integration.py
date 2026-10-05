"""Market evidence in PostgreSQL and the one-off file import (WP-8.3)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work
from app.apps.trading.evidence_import import ImportLedger, import_ibkr, import_yahoo
from app.apps.trading.evidence_storage import PostgresEvidenceBackend, PostgresIbkrSessionEvidence
from app.apps.trading.ibkr_evidence import IbkrEvidenceStore
from app.apps.trading.yahoo_evidence import YahooEvidenceStore

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

SESSION = date(2026, 9, 17)
START = datetime(2026, 9, 17, 13, 31, tzinfo=timezone.utc)


@pytest.fixture()
def database():
    db = PostgresDatabase(
        DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2,
                         application_name="omnix-market-evidence-tests")
    )
    try:
        ensure_local_identity(db)
        yield db
    finally:
        db.close()


def _uow(database):
    return lambda: unit_of_work(database)


def _record(minute: int, *, close: str = "10", received_minutes: int = 2) -> dict[str, str]:
    start = START + timedelta(minutes=minute)
    return {
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": close, "high": close, "low": close, "close": close, "volume": "100",
        "session": "regular",
        "provider_event_id": str(int(start.timestamp())),
        "received_at": (start + timedelta(minutes=received_minutes)).isoformat(),
    }


def test_yahoo_revisions_and_counters_round_trip(database) -> None:
    symbol = f"T{uuid.uuid4().hex[:6].upper()}"
    backend = PostgresEvidenceBackend(uow_factory=_uow(database))
    store = YahooEvidenceStore(backend)

    assert backend.add_revisions(symbol, SESSION, [_record(0, received_minutes=5), _record(1)]) == 2
    # The same content seen earlier only moves its first receipt back.
    assert backend.add_revisions(symbol, SESSION, [_record(0, received_minutes=2)]) == 0
    assert backend.add_revisions(symbol, SESSION, [_record(0, close="11", received_minutes=30)]) == 1

    bars = store.load_market_bars(
        f"equity:NASDAQ:{symbol}", start=START, end=START + timedelta(minutes=2),
        knowledge_mode="causal_replay", known_by=START + timedelta(minutes=10),
    )
    assert [str(bar.close) for bar in bars] == ["10", "10"]
    assert bars[0].received_at == START + timedelta(minutes=2)

    before = backend.counters("yahoo").get("acquisition_attempt_count", 0)
    store.record_acquisition(attempted=2)
    YahooEvidenceStore(backend).record_acquisition(attempted=3)
    assert backend.counters("yahoo")["acquisition_attempt_count"] == before + 5

    store.record_evaluation_outcome(repaired=True, unresolved=True, session_date=SESSION, reason="GAP")
    metrics = store.session_diagnostics(SESSION)
    assert metrics["repaired_but_blocked_evaluation_count"] >= 1
    assert metrics["blocked_reason_counts"]["GAP"] >= 1


def test_ibkr_session_evidence_is_shared_and_complete(database) -> None:
    session = date(2400, 1, 1) + timedelta(days=uuid.uuid4().int % 100_000)
    sessions = PostgresIbkrSessionEvidence(uow_factory=_uow(database))
    first = IbkrEvidenceStore(sessions, flush_events=10, flush_seconds=3600)
    second = IbkrEvidenceStore(sessions, flush_events=2)

    first.record_missing_quote(session, "NO_DATA")
    second.record_missing_quote(session, "NO_DATA")
    first.record_subscription_error(session, "DENIED")

    diagnostics = second.session_diagnostics(session)
    assert diagnostics["missing_quote_count"] == 1  # first's queue is not applied yet
    first.flush()
    diagnostics = second.session_diagnostics(session)
    assert diagnostics["missing_quote_count"] == 2
    assert diagnostics["reason_counts"] == {"DENIED": 1, "NO_DATA": 2}


def test_the_file_evidence_import_is_complete_and_can_be_rerun(database, tmp_path) -> None:
    symbol = f"I{uuid.uuid4().hex[:6].upper()}"
    bars_dir = tmp_path / "yahoo" / "bars" / f"{symbol}-digest"
    bars_dir.mkdir(parents=True)
    legacy = _record(0)  # schema v1: one record per minute
    duplicates = [_record(1, received_minutes=minutes) for minutes in (2, 7, 9)]  # one bar seen three times
    revised = _record(1, close="12", received_minutes=20)
    (bars_dir / f"{SESSION.isoformat()}.json").write_text(json.dumps({
        "schema_version": 2, "provider": "yahoo", "symbol": symbol, "session_date": SESSION.isoformat(),
        "bars": {legacy["start_time"]: legacy, duplicates[0]["start_time"]: [*duplicates, revised]},
    }), encoding="utf-8")
    ibkr_session = date(2401, 1, 1) + timedelta(days=uuid.uuid4().int % 100_000)
    (tmp_path / "ibkr" / "sessions").mkdir(parents=True)
    (tmp_path / "ibkr" / "sessions" / f"{ibkr_session.isoformat()}.json").write_text(
        json.dumps({"provider": "ibkr", "missing_quote_count": 4, "reason_counts": {"NO_DATA": 4}}), encoding="utf-8"
    )
    backend = PostgresEvidenceBackend(uow_factory=_uow(database))
    sessions = PostgresIbkrSessionEvidence(uow_factory=_uow(database))
    ledger = ImportLedger(uow_factory=_uow(database))

    first = import_yahoo(tmp_path / "yahoo", backend=backend, ledger=ledger, report=lambda _line: None)
    again = import_yahoo(tmp_path / "yahoo", backend=backend, ledger=ledger, report=lambda _line: None)

    assert first["revisions"] == 3  # legacy, the deduplicated bar, its revision
    assert again["skipped_files"] == 1 and again["revisions"] == 0
    rows = backend.revisions(symbol, SESSION)
    assert sorted(row["close"] for row in rows) == ["10", "10", "12"]
    assert min(row["received_at"] for row in rows if row["start_time"] == duplicates[0]["start_time"]) == duplicates[0]["received_at"]

    assert import_ibkr(tmp_path / "ibkr", sessions=sessions, ledger=ledger)["files"] == 1
    assert import_ibkr(tmp_path / "ibkr", sessions=sessions, ledger=ledger)["skipped_files"] == 1
    assert IbkrEvidenceStore(sessions).session_diagnostics(ibkr_session)["missing_quote_count"] == 4
