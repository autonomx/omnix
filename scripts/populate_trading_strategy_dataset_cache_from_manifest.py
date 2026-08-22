from __future__ import annotations

"""Populate frozen strategy backtest datasets from an audited candidate manifest.

This is intentionally a test/evidence utility. The manifest comes from a prior
causal historical reconstruction, so a parameter sweep can reuse that exact
candidate set without repeatedly scanning every currently active US equity.
Only the listed symbols' historical daily/premarket/regular-session bars are
requested. The resulting BacktestSessionDataset fingerprint is compared with the
source run before it is admitted to the reusable cache.
"""

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.trading.gapper_dataset import freeze_gapper_universe
from app.trading.historical_gapper_reconstruction import (
    _alpaca_bars,
    _minute_candidate,
    _previous_close_map,
)
from app.trading.providers.alpaca_iex import alpaca_iex_auth_headers
from app.trading.strategy_backtest import freeze_backtest_session
from app.trading.strategy_historical_bars import alpaca_historical_session_bars
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _write_cached_dataset,
)
from scripts.run_trading_strategy_liquidity_sweep_resilient import _ActionsHistoricalRuntime


_ET = ZoneInfo("America/New_York")
_PREMARKET_OPEN = time(4, 0)
_SCAN_TIME = time(9, 20)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate frozen strategy datasets from an audited candidate manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset-cache-dir", required=True)
    parser.add_argument("--assumed-spread-bps", default="40")
    parser.add_argument("--minimum-premarket-dollar-volume", default="250000")
    return parser.parse_args()


def _instrument_parts(instrument_id: str) -> tuple[str, str]:
    parts = instrument_id.split(":")
    if len(parts) < 3 or parts[0] != "equity":
        raise ValueError(f"unsupported manifest instrument id: {instrument_id}")
    return parts[-2].upper(), parts[-1].upper()


def main() -> int:
    args = _parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_sessions = manifest.get("sessions")
    if not isinstance(raw_sessions, dict) or not raw_sessions:
        raise ValueError("candidate manifest has no sessions")

    assumed_spread_bps = Decimal(args.assumed_spread_bps)
    strategy = strict_v11_strategy(
        minimum_premarket_dollar_volume=Decimal(args.minimum_premarket_dollar_volume)
    )
    namespace, basis = _cache_namespace(strategy, assumed_spread_bps)
    cache_root = Path(args.dataset_cache_dir)
    session_cache_dir = cache_root / namespace
    session_cache_dir.mkdir(parents=True, exist_ok=True)
    (session_cache_dir / "cache-basis.json").write_text(
        json.dumps(basis, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (session_cache_dir / "candidate-manifest-source.json").write_text(
        json.dumps(
            {
                "source_workflow_run_id": manifest.get("source_workflow_run_id"),
                "source_head_sha": manifest.get("source_head_sha"),
                "source_strategy_version": manifest.get("source_strategy_version"),
                "scan_time_et": manifest.get("scan_time_et"),
                "manifest_path": str(manifest_path),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    session_dates = sorted(date.fromisoformat(value) for value in raw_sessions)
    missing_dates: list[date] = []
    for session_date in session_dates:
        cache_path = _dataset_cache_path(session_cache_dir, session_date)
        if cache_path.exists():
            cached = _load_cached_dataset(cache_path, session_date)
            expected = str(raw_sessions[session_date.isoformat()].get("dataset_fingerprint") or "")
            if expected and cached.dataset_fingerprint != expected:
                raise ValueError(
                    f"cached dataset differs from audited source for {session_date}: "
                    f"{cached.dataset_fingerprint} != {expected}"
                )
            print(f"Manifest cache hit {session_date}: {cached.dataset_fingerprint}")
            continue
        missing_dates.append(session_date)

    if not missing_dates:
        print(f"All {len(session_dates)} audited sessions already exist in the frozen cache.")
        return 0

    # Only request symbols that are actually present in the audited candidate set.
    all_symbols: set[str] = set()
    assets_by_session: dict[date, list[dict[str, str]]] = {}
    for session_date in missing_dates:
        entries = raw_sessions[session_date.isoformat()]["candidates"]
        assets: list[dict[str, str]] = []
        for entry in entries:
            exchange, symbol = _instrument_parts(str(entry["instrument_id"]))
            all_symbols.add(symbol)
            assets.append({"symbol": symbol, "exchange": exchange, "status": "active", "tradable": True})
        assets_by_session[session_date] = assets

    headers = alpaca_iex_auth_headers()
    runtime = _ActionsHistoricalRuntime("alpaca_manifest_dataset_population")
    daily_start = datetime.combine(min(missing_dates) - timedelta(days=10), time(0, 0), tzinfo=_ET).astimezone(timezone.utc)
    daily_end = datetime.combine(max(missing_dates) + timedelta(days=1), time(0, 0), tzinfo=_ET).astimezone(timezone.utc)
    print(f"Fetching prior daily bars for {len(all_symbols)} audited symbols")
    daily = _alpaca_bars(
        runtime,
        headers,
        sorted(all_symbols),
        timeframe="1Day",
        start=daily_start,
        end=daily_end,
        chunk_size=25,
    )

    for session_date in missing_dates:
        session = raw_sessions[session_date.isoformat()]
        entries = sorted(session["candidates"], key=lambda item: int(item["discovery_rank"]))
        assets = assets_by_session[session_date]
        previous_close = _previous_close_map(assets, daily, session_date=session_date)
        symbols = [str(asset["symbol"]).upper() for asset in assets]
        missing_close = [symbol for symbol in symbols if symbol not in previous_close]
        if missing_close:
            raise ValueError(f"missing audited prior closes for {session_date}: {','.join(missing_close)}")

        scan_at = datetime.combine(session_date, _SCAN_TIME, tzinfo=_ET).astimezone(timezone.utc)
        minute_start = datetime.combine(session_date - timedelta(days=10), _PREMARKET_OPEN, tzinfo=_ET).astimezone(timezone.utc)
        print(f"Fetching premarket/TOD history for {session_date}: {len(symbols)} audited symbols")
        minute = _alpaca_bars(
            runtime,
            headers,
            symbols,
            timeframe="1Min",
            start=minute_start,
            end=scan_at + timedelta(minutes=1),
            chunk_size=25,
        )

        candidates = []
        asset_by_symbol = {str(asset["symbol"]).upper(): asset for asset in assets}
        for entry in entries:
            instrument_id = str(entry["instrument_id"])
            _, symbol = _instrument_parts(instrument_id)
            candidate = _minute_candidate(
                asset=asset_by_symbol[symbol],
                symbol=symbol,
                bars=minute.get(symbol, []),
                session_date=session_date,
                scan_time=_SCAN_TIME,
                previous_close=previous_close[symbol],
                config=strategy.config,
                assumed_spread_bps=assumed_spread_bps,
                observed_at=scan_at,
            )
            if candidate is None:
                raise ValueError(f"audited candidate no longer reconstructs at scan time: {session_date} {instrument_id}")
            if candidate.instrument_id != instrument_id:
                raise ValueError(
                    f"audited instrument identity changed for {session_date}: "
                    f"{candidate.instrument_id} != {instrument_id}"
                )
            candidates.append(candidate.model_copy(update={"discovery_rank": int(entry["discovery_rank"])}))

        universe = freeze_gapper_universe(
            universe_id=f"reconstructed-alpaca-{session_date.isoformat()}-0920",
            session_date=session_date,
            evaluation_time=scan_at,
            discovery_source="provider",
            candidates=candidates,
        )
        print(f"Fetching regular-session replay bars for {session_date}")
        regular = alpaca_historical_session_bars(
            universe.candidates,
            session_date,
            runtime=runtime,
        )
        dataset = freeze_backtest_session(
            session_date=session_date,
            universe=universe,
            bars_by_instrument=regular,
        )
        expected = str(session.get("dataset_fingerprint") or "")
        if expected and dataset.dataset_fingerprint != expected:
            raise ValueError(
                f"refetched dataset differs from audited source for {session_date}: "
                f"{dataset.dataset_fingerprint} != {expected}"
            )
        cache_path = _dataset_cache_path(session_cache_dir, session_date)
        _write_cached_dataset(cache_path, dataset)
        print(f"Cached {session_date}: {dataset.dataset_fingerprint}")

    print(f"Frozen cache populated for {len(session_dates)} audited sessions under {session_cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
