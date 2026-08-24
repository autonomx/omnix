from __future__ import annotations

"""Fast V9 cross-check at the original 11:30 ET entry cutoff only.

This is mathematically sufficient to answer whether restoring the full intended
morning window can rescue V8 regime-3 starvation. Shorter cutoff variants can
only remove signals that the 11:30 version is allowed to take; they cannot
create a signal absent at 11:30. The 34 exact V8 survivors and all other rules
remain unchanged. External April/May data is excluded.
"""

import argparse
import csv
import json
from dataclasses import replace
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import scripts.run_trading_strategy_failed_selloff_v8_orderly_base as _v8
import scripts.run_trading_strategy_failed_selloff_v8_continuity as _v8c
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace, _dataset_cache_path, _load_cached_dataset, _trading_dates


def _dec(value, fallback="-999"):
    return Decimal(fallback) if value is None else Decimal(str(value))


def _positive(row):
    return int(row["trade_count"]) >= 1 and _dec(row.get("expectancy_r")) > 0 and _dec(row.get("pnl"), "0") > 0


def _worst(row):
    return min((Decimal(str(t["r_multiple"])) for t in row.get("trades") or []), default=Decimal("-999"))


def _id(base, gates):
    return f"v9-1130-{_v8._variant_id(base, gates)[3:]}"


def _load(cache, start, end):
    out = []
    for d in _trading_dates(start, end):
        path = _dataset_cache_path(cache, d)
        if not path.exists():
            raise FileNotFoundError(path)
        out.append(_load_cached_dataset(path, d))
    return out


def _run(base, gates, datasets, *, initial_cash, spread):
    row = _v8._run_variant(base, gates, datasets, initial_cash=initial_cash, spread=spread)
    row["variant_id"] = _id(base, gates)
    return row


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--output-dir", default="artifacts/failed-selloff-v9-1130-fast")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="40")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    _v8._v7._result = _v8._normalized_result
    _v8._bt.evaluate_gap_pullback = _v8._orderly_base_evaluate
    _v8._bt._find_trade = _v8._v4._managed_find_trade
    cash = Decimal(args.initial_cash); spread = Decimal(args.assumed_spread_bps)
    namespace, _ = _cache_namespace(strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread)
    cache = Path(args.dataset_cache_dir) / namespace
    b1 = _load(cache, date(2026,5,26), date(2026,6,18))
    b2 = _load(cache, date(2026,6,26), date(2026,7,23))
    b3 = _load(cache, date(2026,7,24), date(2026,8,21))
    all_data = b1+b2+b3
    variants = [(replace(base, last_entry_et=time(11,30)), gates) for base,gates in _v8._grid() if _v8._variant_id(base,gates) in _v8c.SURVIVOR_IDS]
    if len(variants) != 34 or len(all_data) != 58:
        raise ValueError(f"expected 34 variants / 58 sessions, got {len(variants)} / {len(all_data)}")

    state = {_id(*v): {"base":v[0],"gates":v[1],"r3":None,"r1":None,"r2":None,"full":None} for v in variants}
    s3=[]
    print(f"V9 11:30 regime3: {len(variants)} variants")
    for i,(base,gates) in enumerate(variants,1):
        r=_run(base,gates,b3,initial_cash=cash,spread=spread); state[_id(base,gates)]["r3"]=r
        if _positive(r): s3.append((base,gates))
        if i%8==0 or i==len(variants): print(f"  {i}/{len(variants)}")
    print(f"regime3 positive: {len(s3)}")

    s1=[]
    for base,gates in s3:
        r=_run(base,gates,b1,initial_cash=cash,spread=spread); state[_id(base,gates)]["r1"]=r
        if _positive(r): s1.append((base,gates))
    print(f"regime1 transfer positive: {len(s1)}")
    s2=[]
    for base,gates in s1:
        r=_run(base,gates,b2,initial_cash=cash,spread=spread); state[_id(base,gates)]["r2"]=r
        if _positive(r): s2.append((base,gates))
    print(f"regime2 transfer positive: {len(s2)}")

    final=[]
    for base,gates in s2:
        r=_run(base,gates,all_data,initial_cash=cash,spread=spread); state[_id(base,gates)]["full"]=r
        if int(r["trade_count"])>=8 and _dec(r.get("expectancy_r"))>0 and _dec(r.get("pnl"),"0")>0 and _worst(r)>Decimal("-1.75") and _dec(r.get("max_drawdown_pct"),"999")<Decimal("2"):
            final.append((base,gates))
    final.sort(key=lambda v:(_dec(state[_id(*v)]["full"].get("expectancy_r")),_dec(state[_id(*v)]["full"].get("pnl"),"0"),_worst(state[_id(*v)]["full"])),reverse=True)

    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    serial=[]
    for base,gates in variants:
        b=state[_id(base,gates)]
        serial.append({"variant_id":_id(base,gates),"parameters":{"minimum_premarket_dollar_volume":str(base.minimum_premarket_dollar_volume),"minimum_l1_to_b1_minutes":gates.minimum_l1_to_b1_minutes,"maximum_l2_to_signal_minutes":gates.maximum_l2_to_signal_minutes,"maximum_pullback_to_bounce_volume_ratio":str(gates.maximum_pullback_to_bounce_volume_ratio),"last_entry_et":"11:30:00"},"regime3":b["r3"],"regime1":b["r1"],"regime2":b["r2"],"full":b["full"]})
    (out/"results.json").write_text(json.dumps(serial,indent=2,default=str)+"\n",encoding="utf-8")
    with (out/"comparison.csv").open("w",newline="",encoding="utf-8") as h:
        fields=["variant_id","r3_trades","r3_exp","r3_pnl","r1_trades","r1_exp","r1_pnl","r2_trades","r2_exp","r2_pnl","full_trades","full_exp","full_pnl","full_dd","worst_r"]
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        for x in serial:
            r3,r1,r2,f=x["regime3"],x["regime1"],x["regime2"],x["full"]
            w.writerow({"variant_id":x["variant_id"],"r3_trades":r3["trade_count"],"r3_exp":r3["expectancy_r"],"r3_pnl":r3["pnl"],"r1_trades":None if r1 is None else r1["trade_count"],"r1_exp":None if r1 is None else r1["expectancy_r"],"r1_pnl":None if r1 is None else r1["pnl"],"r2_trades":None if r2 is None else r2["trade_count"],"r2_exp":None if r2 is None else r2["expectancy_r"],"r2_pnl":None if r2 is None else r2["pnl"],"full_trades":None if f is None else f["trade_count"],"full_exp":None if f is None else f["expectancy_r"],"full_pnl":None if f is None else f["pnl"],"full_dd":None if f is None else f["max_drawdown_pct"],"worst_r":None if f is None else str(_worst(f))})
    lines=["# V9 fast 11:30 ET cross-check","","Revealed-data only; external April/May holdout excluded.","",f"- Starting exact V8 survivors: {len(variants)}",f"- Regime-3 positive-with-trade: {len(s3)}",f"- Regime-1 transfer positive: {len(s1)}",f"- Regime-2 transfer positive: {len(s2)}",f"- Full-rule survivors: {len(final)}",""]
    if final:
        lines += ["| Rank | Variant | R3 trades/exp | R1 trades/exp | R2 trades/exp | Full trades | Full expR | Full P&L | DD% | Worst R |","|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for rank,v in enumerate(final,1):
            b=state[_id(*v)]; r3,r1,r2,f=b["r3"],b["r1"],b["r2"],b["full"]
            lines.append(f"| {rank} | `{_id(*v)}` | {r3['trade_count']} / {r3['expectancy_r']} | {r1['trade_count']} / {r1['expectancy_r']} | {r2['trade_count']} / {r2['expectancy_r']} | {f['trade_count']} | {f['expectancy_r']} | {f['pnl']} | {f['max_drawdown_pct']} | {_worst(f)} |")
        v=final[0]; f=state[_id(*v)]["full"]; lines += ["","## Conclusion","",f"Freeze `{_id(*v)}` before external validation.",f"Revealed result: {f['trade_count']} trades, {f['expectancy_r']}R, P&L {f['pnl']}, DD {f['max_drawdown_pct']}%."]
    else:
        lines += ["## Conclusion","","Restoring the full 11:30 ET window does not produce a promotable V9 candidate. Keep the external holdout sealed."]
    (out/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print((out/"summary.md").read_text(encoding="utf-8"))
    return 0

if __name__=="__main__": raise SystemExit(main())
