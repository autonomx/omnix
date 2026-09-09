# Stoch execution-cost SHADOW accounting

Status: research-only. No order authority.

The 3-minute Stoch trend-capture strategy now distinguishes its chart-reference
return from its executable return.

For every actionable SHADOW entry/exit window, Omnix captures point-in-time
Alpaca IEX quote evidence and reuses the shared paper-execution-v2 fill kernel.

Execution assumptions:

- market entry consumes the ask and then applies configured adverse slippage;
- market exit consumes the bid and then applies configured adverse slippage;
- stale, halted, or execution-ineligible observations do not produce fills;
- displayed top-of-book size is subject to the existing liquidity-participation
  cap;
- quote captures more than 60 seconds after the causal action time are rejected
  as late rather than backfilled.

The entry evidence event now includes an execution simulation. Exit actions are
persisted as stoch_trend_execution events. Once the chart lifecycle is complete,
stoch_trend_execution_summary reports:

- gross chart-reference return;
- net bid/ask/slippage-adjusted return;
- execution drag in percentage points;
- simulated entry and weighted exit prices;
- observed spread statistics.

Spread tiers are descriptive:

- <= 50 bps: tight;
- <= 100 bps: acceptable;
- <= 150 bps: expensive;
- > 150 bps: extreme.

The existing configured maximum-spread rule remains the entry veto. Exit
evidence is never improved with a later quote if the causal action window was
missed.

All records remain research_only=true and execution_authority=false.
