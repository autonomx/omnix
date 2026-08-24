from __future__ import annotations

import json
from decimal import Decimal

from app.trading.trade_logging import trade_log, trade_log_path


def test_trade_audit_log_writes_jsonl_and_redacts_secrets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_TRADE_LOG_DIR", str(tmp_path / "trade"))
    monkeypatch.setenv("OMNIX_TRADE_AUDIT_LOGGING", "1")

    trade_log(
        "auto_trading",
        "risk_decision",
        strategy_id="strategy-1",
        quantity=Decimal("12.5"),
        api_key="should-not-leak",
        nested={
            "authorization": "Bearer should-not-leak-either",
            "safe": "visible",
            "credentials": {"username": "also-hidden-by-parent", "secret": "hidden"},
        },
    )

    path = trade_log_path("auto_trading")
    raw = path.read_text(encoding="utf-8").strip()
    payload = json.loads(raw)

    assert path.parent == tmp_path / "trade"
    assert path.name == "auto_trading.jsonl"
    assert payload["channel"] == "auto_trading"
    assert payload["event"] == "risk_decision"
    assert payload["strategy_id"] == "strategy-1"
    assert payload["quantity"] == "12.5"
    assert payload["api_key"] == "<redacted>"
    assert payload["nested"]["authorization"] == "<redacted>"
    assert payload["nested"]["credentials"] == "<redacted>"
    assert payload["nested"]["safe"] == "visible"
    assert "should-not-leak" not in raw


def test_trade_audit_log_can_be_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_TRADE_LOG_DIR", str(tmp_path / "trade"))
    monkeypatch.setenv("OMNIX_TRADE_AUDIT_LOGGING", "0")

    trade_log("backtest", "backtest_requested", strategy_id="strategy-1")

    assert not trade_log_path("backtest").exists()
