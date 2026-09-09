# Market Evidence V3 — Finviz Membership Authority

`market-evidence-v3-finviz-membership` is the prospective data and execution-authority contract for managed Finviz V2 gap-pullback trading.

The central rule is simple: **the frozen Finviz Top Gainers cohort owns premarket membership; premarket enrichment does not own trading authority.** Once the configured ranked Finviz cohort is captured, Omnix stays armed for those symbols. Missing Yahoo chart enrichment, TOD-RVOL, premarket volume/dollar volume, float, market cap, or frozen spread is recorded as research-quality evidence and must not permanently disable the trading day.

## Authority model

The strategy remains deterministic. AI, Stoch overlays, catalyst research, premarket liquidity, TOD-RVOL, frozen spreads, and diagnostic fallbacks never place or authorize an order.

A strategy-origin BUY reaches the paper repository only after a `trade_authorization` assessment is persisted immediately in front of `place_order`. Protective and force-flat SELL orders retain their independent safety path.

For managed Finviz V2, authorization requires:

- the candidate belongs to the immutable ranked Finviz cohort and has a materialized source disposition;
- the source cohort is fully accounted for;
- causal regular-session 1-minute bar coverage is current and contiguous;
- deterministic V2 state is `entry_ready`;
- a fresh authoritative execution observation exists;
- the live execution observation is eligible and passes the entry-time spread limit;
- deterministic risk sizing is allowed;
- the entry window is open;
- the authoritative execution provider is ready;
- provider circuit/readiness is clear;
- the strategy kill switch is clear;
- V2 qualification authorizes AUTO PAPER when the strategy is in AUTO PAPER mode;
- the strategy profile fingerprint matches the active strategy policy.

Premarket liquidity fields and frozen spread are deliberately **not** BUY-authority predicates for managed Finviz V2.

## Immutable Top-Gainers membership

At the configured scan time, Omnix performs one atomic Finviz Top Gainers capture and freezes the configured ranked cohort (normally Top 5). That membership cannot be replaced later with a different Finviz scan merely because another provider was temporarily unavailable.

For managed Finviz V2, gap and price thresholds no longer remove members from this frozen Top-Gainers cohort. Those values may still be recorded for research.

Every ranked source symbol receives a `SourceMemberDisposition`. If Yahoo enrichment is available, Omnix resolves the normal canonical US equity identity. If enrichment is unavailable, membership mode preserves the symbol using a venue-neutral provisional identity such as `equity:US:XYZ` and records research-quality flags instead of dropping the symbol.

This means a Yahoo outage cannot silently turn a Top-5 cohort into a Top-4 survivor cohort.

## Premarket enrichment is research-only

Omnix still attempts to collect useful morning features, including:

- premarket volume and dollar volume;
- TOD-RVOL and its historical baseline;
- market cap and float;
- catalyst and dilution evidence;
- frozen bid/ask spread.

Where available, prospective liquidity continues to prefer a consistent same-feed Alpaca IEX calculation. Missing or suspicious values remain typed and observable.

For managed Finviz V2, however, the following no longer reject a candidate solely because they are missing or below a configured research threshold:

- `market_data_complete=false`;
- `PREMARKET_DOLLAR_VOLUME_LOW`;
- `TOD_RVOL_MISSING` / `TOD_RVOL_LOW`;
- frozen `SPREAD_MISSING` / `SPREAD_TOO_WIDE`;
- missing Yahoo chart enrichment;
- premarket gap/price filter failures after the symbol has already been selected by the frozen Finviz ranking.

Explicit catalyst, dilution, or float requirements remain enforceable when a strategy profile deliberately enables them.

## Automatic recovery after the open

A temporary regular-session data failure is a waiting condition, not a permanent daily veto.

The monitor repeatedly requests the current causal one-minute history for every frozen cohort member. If the configured history provider is unavailable at 09:30 but begins returning valid contiguous bars at 09:35, the same frozen symbols immediately resume deterministic evaluation from the data then available.

Managed Finviz V2 uses the actual regular-session opening price as the structural impulse reference. Provisional or incomplete premarket prices therefore cannot distort L1/B1/L2 failed-selloff geometry.

Canonical AUTO PAPER remains fail-closed while its required live bar history is unavailable. SHADOW research may use the documented Alpaca-IEX history fallback, but a research fallback does not silently become execution authority.

## Live execution remains the hard gate

Recovering chart bars is not enough to place an order. At an actual entry attempt Omnix still requires a fresh authoritative execution observation, including usable bid/ask and an entry-time spread inside the configured risk limit.

Thus a sequence such as:

```text
06:15 PT  Finviz Top 5 captured
06:15 PT  Yahoo premarket enrichment unavailable
06:30 PT  Yahoo regular bars temporarily unavailable
06:35 PT  causal 1m bars recover
06:42 PT  V2 reaches entry_ready
06:42 PT  fresh Alpaca IEX execution observation passes spread/risk gates
           -> BUY may be authorized
```

is valid. The 06:15 provider outage does not permanently poison the day.

## Trading evaluability vs qualification evidence

Trading recovery and AUTO PAPER promotion evidence are intentionally different contracts.

A fully accounted Finviz cohort can be **tradable** even when some morning research fields were incomplete. That lets the live strategy recover when regular-session data becomes healthy.

Promotion evidence stays stricter. Sessions with incomplete morning research evidence do not count as clean qualification sessions. This prevents a data outage from improving promotion statistics while avoiding the opposite failure mode of disabling the trading day.

## AI research behavior

AI SHADOW remains research-only with `execution_authority=false`. It may consume causal market, indicator, cohort, and execution-quality evidence, but no AI action can bypass deterministic strategy/risk/order authority.

## Version reset

This change materially alters strategy evidence semantics, so it intentionally resets policy identity:

- market evidence: `market-evidence-v3-finviz-membership`;
- qualification: `v2-prospective-qualification-3`;
- replay: `v2-shadow-replay-3`.

Old qualification/replay evidence cannot silently authorize the new policy.

## Regression evidence

Focused coverage proves that a managed Finviz candidate with missing Yahoo/TOD-RVOL/premarket fields remains armed and waits for the regular session rather than being rejected, and that a Finviz symbol is still materialized when Yahoo enrichment is unavailable.

```powershell
python -m pytest `
  src/tests/trading/test_trading_market_evidence_v2.py `
  src/tests/trading/test_trading_finviz_gapper_discovery.py `
  src/tests/trading/test_trading_strategy_universe_archiver.py `
  src/tests/trading/test_trading_gap_pullback_v2.py `
  src/tests/trading/test_trading_auto_paper_e2e_replay.py `
  -q --tb=short
```

The normal `Omnix Trading terminal gates` workflow runs the complete Trading backend, frontend, typecheck, browser smoke, and generated API checks on the immutable PR head. PostgreSQL and Agent Runtime gates run separately.