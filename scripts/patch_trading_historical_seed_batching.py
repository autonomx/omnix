from __future__ import annotations

from pathlib import Path

source_path = Path("src/app/trading/historical_gapper_reconstruction.py")
source = source_path.read_text(encoding="utf-8")
old_constant = '_SCAN_SEED_LOOKBACK_MINUTES = 15\n'
new_constant = '_SCAN_SEED_LOOKBACK_MINUTES = 15\n# A 15-minute seed window yields at most 15 one-minute bars per symbol.\n# 1,000-symbol batches remain bounded by Alpaca pagination while reducing\n# request count versus the old 200-symbol batching.\n_SCAN_SEED_CHUNK_SIZE = 1000\n'
if source.count(old_constant) != 1:
    raise RuntimeError("unexpected scan-seed constant shape")
source = source.replace(old_constant, new_constant)
old_scan = '''        scan_window = _alpaca_bars(\n            self.runtime,\n            self._headers,\n            list(previous_close),\n            timeframe="1Min",\n            start=seed_start,\n            end=scan_at,\n            chunk_size=200,\n        )\n'''
new_scan = '''        scan_window = _alpaca_bars(\n            self.runtime,\n            self._headers,\n            list(previous_close),\n            timeframe="1Min",\n            start=seed_start,\n            end=scan_at,\n            chunk_size=_SCAN_SEED_CHUNK_SIZE,\n        )\n'''
if source.count(old_scan) != 1:
    raise RuntimeError("unexpected broad seed-scan call shape")
source_path.write_text(source.replace(old_scan, new_scan), encoding="utf-8")

test_path = Path("src/tests/trading/test_trading_historical_gapper_reconstruction.py")
test = test_path.read_text(encoding="utf-8")
marker = '''\ndef test_reconstructed_strategy_config_relaxes_only_unavailable_historical_evidence() -> None:\n'''
if test.count(marker) != 1:
    raise RuntimeError("unexpected historical reconstruction test marker")
new_test = r'''

def test_seed_scan_batches_one_thousand_symbols_without_changing_data_contract(monkeypatch) -> None:
    session_date = date(2026, 8, 18)
    symbols = [f"S{index:04d}" for index in range(1001)]

    class BatchRuntime:
        def __init__(self):
            self.minute_seed_requests: list[tuple[str, ...]] = []

        def get(self, url, *, params=None, headers=None, timeout=None, cancellation=None):
            if url.endswith("/v2/assets"):
                return FakeResponse([
                    {"symbol": symbol, "exchange": "NASDAQ", "status": "active", "tradable": True}
                    for symbol in symbols
                ])
            assert url.endswith("/v2/stocks/bars")
            requested = tuple(str(params["symbols"]).split(","))
            if params["timeframe"] == "1Day":
                prior = session_date - timedelta(days=1)
                return FakeResponse({
                    "bars": {
                        symbol: [{"t": f"{prior.isoformat()}T20:00:00Z", "o": 10, "c": 10}]
                        for symbol in requested
                    },
                    "next_page_token": None,
                })
            self.minute_seed_requests.append(requested)
            return FakeResponse({"bars": {}, "next_page_token": None})

    monkeypatch.setattr(
        reconstruction,
        "alpaca_iex_auth_headers",
        lambda: {"APCA-API-KEY-ID": "test-key", "APCA-API-SECRET-KEY": "test-secret"},
    )
    runtime = BatchRuntime()
    config = GapPullbackConfig(
        strategy_version="1.1.0",
        minimum_gap_pct=Decimal("20"),
        minimum_premarket_dollar_volume=Decimal("0"),
        minimum_tod_rvol=Decimal("0"),
        universe_discovery_count=10,
    )

    result = reconstruction.AlpacaHistoricalGapperReconstructor(
        start_date=session_date,
        end_date=session_date,
        config=config,
        assumed_spread_bps=Decimal("40"),
        max_age_days=30,
        clock=datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc),
        runtime=runtime,
    )(
        session_date=session_date,
        scan_time=time(9, 20),
    )

    assert result.snapshot is None
    assert result.fidelity == "reconstructed_current_listings_iex"
    assert [len(batch) for batch in runtime.minute_seed_requests] == [1000, 1]
    assert reconstruction._SCAN_SEED_CHUNK_SIZE == 1000
'''
test_path.write_text(test.replace(marker, new_test + marker), encoding="utf-8")
print("Applied larger bounded batching for the historical broad seed scan.")
