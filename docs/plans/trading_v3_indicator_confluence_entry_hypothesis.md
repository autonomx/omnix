# Trading V3 research hypothesis — indicator-confluence entry confirmation

Status: **development research only; not selectable; no execution authority**.

This hypothesis was frozen after the user introduced their discretionary entry/exit process using Stochastic RSI, MACD, moving averages and multi-timeframe trend state. It is a new causal hypothesis, not a threshold rescue of the rejected delayed-base experiment. March 2026 remains sealed before this hypothesis is replayed.

## Principle

Price structure remains primary. Indicators are not allowed to manufacture an entry on their own. Instead, an otherwise valid frozen V2 structural entry is admitted only when momentum/trend evidence agrees.

This isolates the question cleanly:

> **Do V2 structural signals perform better when 1-minute momentum and 5-minute trend state are already aligned bullish at the causal signal time?**

Frozen `gap_pullback_v1 2.0.0` is not changed. The experiment wraps its structural signal in a research-only indicator confirmation and keeps the existing deterministic execution/risk/exit model unchanged so any performance difference is attributable to entry selection.

## Server-side indicator definitions

All calculations use finalized bars only and are implemented in `app.trading.indicator_signals` with Decimal arithmetic.

- EMA 9 and EMA 20.
- MACD 12 / 26 / 9.
- Stochastic RSI 14 / 14 / 3 / 3.
- 1-minute and 5-minute snapshots are calculated from the same causal bar prefix.

The old October-February cache contains regular-session data but does not reliably contain enough premarket history to warm up every standard 5-minute oscillator before the 11:30 entry cutoff. Missing 5-minute MACD/Stochastic-RSI values therefore remain explicitly `null`; they are never reconstructed from future or prior-session data.

Prospective SHADOW execution evidence now records the same indicator context when available so future live evidence can include the fuller same-day/premarket history returned by the market service.

## Frozen entry confirmation

The underlying structural signal must first satisfy the exact frozen V2 `entry_ready` state. The research wrapper then requires:

### 1-minute — mandatory

- EMA9 available.
- EMA20 available.
- Price > EMA9.
- EMA9 > EMA20.
- EMA9 rising versus the prior finalized 1-minute bar.
- MACD and signal available, with MACD > signal and non-negative histogram.
- Stochastic RSI %K and %D available, with %K >= %D.

`Stoch RSI > 80` is **not** itself bearish and does not veto entry. The hypothesis cares about direction/alignment, not an overbought label.

### 5-minute — trend confirmation

- EMA9 must be available.
- Price > EMA9.
- EMA9 must be rising.

Longer-warmup 5-minute evidence is a causal **veto when available**:

- if EMA9 <= EMA20, reject;
- if MACD <= signal, reject;
- if Stochastic RSI %K < %D, reject.

If those longer-warmup 5-minute values are unavailable in the historical cache, they are neutral rather than fabricated. Coverage is reported separately so a positive result cannot be misrepresented as full multi-timeframe validation.

## Execution and exit isolation

For this entry experiment only:

- structural stop remains frozen V2 L2 minus 15 bps;
- entry remains the next eligible 1-minute paper fill;
- target remains 1.5R;
- profit protection remains +0.75R arm -> +0.25R protected stop;
- max hold remains 60 minutes;
- force-flat remains authoritative.

Adaptive Stochastic-RSI/MACD/MA exits will be tested separately after entry attribution so entry and exit effects are not confounded.

## Development gate before March

Replay the exact frozen wrapper over **2025-10-01 through 2026-02-27** using the existing 103-session immutable causal cache only.

March may be opened only if the indicator-confirmed sample achieves all of:

- at least **10 trades**;
- expectancy **>= +0.20R/trade**;
- one-sided 90% lower confidence bound **> 0R**;
- maximum drawdown **<= 5R**;
- expectancy strictly better than the unmodified frozen-V2 structural baseline on the same development block.

If the sample has fewer than 10 trades, the result is `inconclusive_low_trade_count`, not a pass. If any other gate fails, the hypothesis is rejected. No indicator-period, vote-count, or threshold rescue is permitted on this development block.

## Data limitations

- Historical reconstruction uses current listings and Alpaca IEX partial-market data, so survivorship/listing bias remains.
- Historical point-in-time catalyst/supply/float evidence is not fabricated.
- The old cache does not provide authoritative historical halt state.
- Standard 5-minute MACD/Stochastic-RSI frequently need more warm-up history than the old regular-session-only cache has before 11:30; missing values are explicitly measured.

Frozen V2 prospective SHADOW qualification remains unchanged and fail-closed.