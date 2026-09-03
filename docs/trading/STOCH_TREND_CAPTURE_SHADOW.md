# Stoch Trend Capture — prospective SHADOW policy

Status: **research-only / SHADOW; no execution authority**.

This policy was added after reviewing the September 2 Finviz Top-5 session. The goal is to capture the common intraday pattern where a volatile gapper becomes oversold on 3-minute Stochastic RSI, recovers, and then trends higher for hours. It deliberately avoids treating the first overbought reading as an automatic full exit once a real uptrend has been proven.

## Frozen v1 policy

Indicator:

- 3-minute finalized bars.
- Stochastic RSI 14 / 14 / 3 / 3.
- Oversold: K <= 20 and D <= 20.
- Overbought: K >= 80 and D >= 80.
- One trade hypothesis per symbol per session.

Entry:

1. Wait for the **first regular-session oversold** reading after the configured strategy entry start.
2. Arm the trade only from that finalized 3-minute bar.
3. Entry reference is the **next 3-minute regular-session bar open**.
4. At the live signal timestamp Omnix also captures authoritative SHADOW execution evidence.
5. The trade is prospectively vetoed when the execution provider reports a halt, ineligible execution, or a spread wider than the server risk ceiling. Missing execution eligibility is fail-closed.

Range/rebound mode:

- If the first later overbought reading occurs **before trend mode is confirmed**, exit the full hypothetical position at the next 3-minute bar open.
- This preserves the simple oversold -> overbought mean-reversion behavior for names that never become sustained trends.

Trend mode:

Trend mode requires all of the following causally:

- at least two rising-low steps in the recent 3-minute structure;
- price above the 3-minute EMA9;
- EMA9 rising;
- price at/above regular-session VWAP.

Once trend mode is active:

- an overbought Stoch RSI reading is treated as **strength, not a full exit**;
- the first later overbought reading banks **25%** at the next 3-minute bar open;
- the remaining **75% runner** stays open while the trend remains intact.

Runner exit:

The runner exits only after a causal trend break or the configured force-flat:

- break of the latest confirmed 3-minute pivot low while price is below a falling EMA9; or
- two consecutive 3-minute closes below EMA9 with EMA9 falling and price below regular-session VWAP;
- otherwise force-flat at the **close/end of the first finalized 3-minute bar whose end crosses the configured cutoff**. For the default 15:55 ET cutoff, that is the 15:54-15:57 bar close; the replay never uses the pre-cutoff 15:54 open.

The combined research return is the quantity-weighted partial + runner exit price.

## Data continuity

The overlay fails closed when finalized regular-session 3-minute bars contain an
internal gap. A halt or missing source interval must never be treated as if EMA,
Stochastic RSI, higher lows, or runner exits evolved continuously across the
missing period. In that case the snapshot moves to
`STOCH_TREND_REGULAR_SESSION_DATA_GAP` and no hypothetical return is produced.

## Authority boundary

This policy does **not**:

- create paper or live orders;
- change the frozen V2 L1 -> B1 -> higher-L2 -> VWAP/B1-break entry authority;
- change V2 risk limits, stops, targets, or promotion thresholds;
- alter the canonical V2 profile fingerprint;
- inherit Yahoo V2 AUTO PAPER qualification.

The Finviz learning preset enables the overlay in SHADOW mode so the Top-5 cohort can collect prospective evidence immediately.

## Evidence events

The monitor persists:

- `stoch_trend_capture`: current causal policy state and replay fields;
- `stoch_trend_capture_entry`: point-in-time authoritative execution/halt/spread eligibility captured exactly when the first oversold signal becomes actionable.

All events include `research_only=true` and `execution_authority=false`.

## Intended evaluation

Score this policy separately from current V2 on prospective sessions:

- eligible signal count;
- trade count after execution veto;
- win rate;
- average/median return;
- expectancy in R after a fixed risk model is added;
- max drawdown;
- percentage of trades that become trend mode;
- runner capture ratio versus session MFE;
- range-mode versus trend-mode performance;
- halt/spread veto outcomes;
- performance versus pure first-oversold -> first-overbought;
- performance versus frozen Omnix V2.

Do not promote from a handful of visually selected winners. The policy should remain SHADOW until a sufficiently large prospective sample demonstrates that the trend-capture overlay improves risk-adjusted outcomes.
