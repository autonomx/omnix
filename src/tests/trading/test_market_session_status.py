from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.trading.api import create_trading_router
from app.apps.trading.catalog import INSTRUMENTS
from app.apps.trading.market_session_status import is_always_open, market_session_status

ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ET)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (_et(2026, 10, 7, 3, 59), "closed"),
        (_et(2026, 10, 7, 4, 0), "pre_market"),
        (_et(2026, 10, 7, 9, 29), "pre_market"),
        (_et(2026, 10, 7, 9, 30), "open"),
        (_et(2026, 10, 7, 15, 59), "open"),
        (_et(2026, 10, 7, 16, 0), "post_market"),
        (_et(2026, 10, 7, 19, 59), "post_market"),
        (_et(2026, 10, 7, 20, 0), "closed"),
        (_et(2026, 10, 10, 12, 0), "closed"),  # Saturday
        (_et(2026, 11, 26, 12, 0), "closed"),  # Thanksgiving
        (_et(2026, 11, 27, 13, 0), "post_market"),  # early close at 13:00
        (_et(2026, 11, 27, 17, 0), "closed"),  # extended trading ends 17:00 on early closes
    ],
)
def test_us_equity_calendars_follow_the_exchange_session(moment: datetime, expected: str) -> None:
    assert market_session_status("XNYS", "equity", moment) == expected
    assert market_session_status("XNAS", "equity", moment) == expected


def test_crypto_is_always_open_and_unknown_calendars_say_so() -> None:
    weekend = _et(2026, 10, 10, 3, 0)
    assert market_session_status("24x7", "crypto", weekend) == "open"
    assert is_always_open("24x7", "crypto")
    # Non-crypto assets fall back to a 24x7 calendar without session rules.
    assert market_session_status("24x7", "equity", weekend) == "unknown"
    assert not is_always_open("24x7", "equity")
    assert market_session_status("XLON", "equity", weekend) == "unknown"


def test_market_session_status_requires_an_aware_moment() -> None:
    with pytest.raises(ValueError):
        market_session_status("XNYS", "equity", datetime(2026, 10, 7, 12, 0))


def test_market_status_endpoint_reports_the_instrument_session() -> None:
    equity = next(item for item in INSTRUMENTS if item.session_calendar == "XNYS")
    crypto = next(item for item in INSTRUMENTS if item.asset_class == "crypto")
    moment = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
    app = FastAPI()
    app.include_router(create_trading_router(clock=lambda: moment))
    client = TestClient(app)

    response = client.get("/api/trading/market-status", params={"instrument_id": equity.instrument_id})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "post_market"
    assert body["always_open"] is False
    assert body["session_calendar"] == "XNYS"
    assert body["exchange_timezone"] == equity.exchange_timezone

    crypto_body = client.get("/api/trading/market-status", params={"instrument_id": crypto.instrument_id}).json()
    assert crypto_body["status"] == "open"
    assert crypto_body["always_open"] is True

    missing = client.get("/api/trading/market-status", params={"instrument_id": "unknown:instrument"})
    assert missing.status_code == 404
