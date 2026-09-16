# Leader Momentum v1.3 research phase

This phase is **research-only**.  `leader-momentum-continuation-v1.2` remains the
frozen SHADOW policy.  Do not modify its thresholds, modes, stops, exits, or
re-entry rules while running this phase.

The corrected evolving-Top-Gainers replay showed three useful facts:

1. dynamic Top-20 discovery recovers most eventual daily leaders and admits the
   important monster runners before their Leader Momentum signals;
2. Leader Momentum materially enriches for stocks with meaningful continuation
   still available; and
3. aggregate v1.2 economics remain weak because losses are concentrated in
   momentum-compression entries and second trades/re-entries.

The next experiment must therefore isolate those structural choices without
retuning the policy.

## Shared research modules

Use:

- `app.trading.strategy_evolving_top_gainers`
- `app.trading.strategy_evolving_top_gainers_research`
- `app.trading.strategy_leader_momentum_research`

Do not duplicate their logic in a local replay script.

## Point-in-time population authority

Every historical session must have a `HistoricalPopulationManifest` before the
leaderboard is reconstructed.

A manifest is valid for inference only when:

- `point_in_time=True`;
- `outcome_conditioned=False`;
- every observation symbol is contained in the manifest;
- every resulting leaderboard member is contained in the manifest; and
- the manifest and replay refer to the same exchange session.

A current active Alpaca asset catalog is **not** point-in-time historical
population evidence.  It may be used for exploratory debugging only and must be
marked `point_in_time=False`, which causes strict inference to fail closed.

Preferred authorities, in order:

1. archived per-session Omnix/Finviz observable population;
2. historically listed/tradable SIP population for that session;
3. another immutable historical listing source captured independently of the
   end-of-day winner labels.

Run the final experiment through `replay_evolving_top_gainers_strict(...)`.
Do not append known winners that were outside the frozen session population.

## Frozen discovery rule

Primary discovery remains:

- Top 20 gainers;
- five-minute ranking cadence;
- causal price divided by previous regular-session close;
- first evaluation 09:35 ET;
- last new-entry evaluation 15:30 ET.

Top-10 and Top-5 membership remain diagnostics, not tuned admission rules.

## Causal leaderboard trajectory

For every Leader Momentum signal call `leaderboard_trajectory_at(...)` using the
signal timestamp.  Export at least:

- current Top-N membership;
- current rank;
- current gain percent;
- best rank achieved so far;
- best gain achieved so far;
- 5-minute rank improvement;
- 15-minute rank improvement;
- 5-minute gain acceleration;
- 15-minute gain acceleration;
- minutes since first Top-20 entry;
- snapshots spent Top-10;
- consecutive Top-10 snapshots; and
- whether Top-5 had been reached before the signal.

Positive `rank_improvement_*` means the symbol is climbing toward rank 1.
These fields are explanatory features only in this phase.  Do not create a new
rank threshold from the same sample.

## Required ablation matrix

Run the same frozen population, cache, discovery timestamps, context and fills
through all four variants from `strategy_leader_momentum_research`:

| Variant | Modes | Max trades |
| --- | --- | ---: |
| `BASELINE_V1_2` | controlled pullback + momentum compression | 2 |
| `CONTROLLED_PULLBACK_ONLY` | controlled pullback | 2 |
| `SINGLE_TRADE_ONLY` | both frozen modes | 1 |
| `CONTROLLED_PULLBACK_SINGLE_TRADE` | controlled pullback | 1 |

Before interpreting results, run `assert_baseline_parity(...)` on every evaluated
symbol/session or on a deterministic representative sample large enough to fail
closed on any implementation drift.  The baseline research variant must match
the frozen v1.2 evaluator exactly.

These are structural ablations, not candidate v1.3 policy selections.  Do not
promote the best in-sample variant directly.

## Chronological validation

Avoid choosing a variant from the same 62-session sample and declaring it the
new policy.

Report at minimum:

- June;
- July;
- August;
- September through the available cutoff;
- June through August 12;
- August 13 through September 11.

If enough independent sessions are available, use an expanding or rolling
walk-forward procedure where a proposed rule is selected only on earlier data
and measured on later untouched sessions.

## Required economics

For every variant report:

- symbol observations;
- trade executions;
- first versus second trades;
- Mode A versus Mode B;
- win/loss/flat count;
- mean and median return;
- expectancy;
- profit factor;
- MFE and MAE;
- realized/MFE capture;
- exit-reason distribution;
- final Top-5 versus other Top-20 entrants;
- +10/+20/+30/+50/+100 percent remaining-continuation rates;
- 0/40/80/120/200 bps round-trip friction sensitivity;
- five-slot portfolio result; and
- top-1/top-3/top-5 contribution and results with those trades removed.

Do not suppress CPHI or any other tail observation.  Tail dependence is an
explicit property to measure.

## Initial-stop analysis

For every initial-stop loss record MFE before stop.  Split losses into at least:

- MFE < +5%;
- +5% to < +10%;
- +10% to < +20%;
- >= +20%.

If most losses never achieve positive excursion, treat that as entry-selection
evidence rather than an exit-management problem.

## Re-entry analysis

Report first and second trades independently, including:

- count;
- P/L;
- expectancy;
- win rate;
- MFE/MAE;
- setup mode; and
- leaderboard trajectory at each signal.

A single-trade ablation is intended to measure the cost of the current re-entry
authority.  It does not authorize changing `MAX_TRADES` in v1.2.

## Integrity gates

The experiment is invalid for inference if any of these occur:

- population manifest is not point-in-time;
- population is outcome-conditioned;
- observation or leaderboard symbol falls outside the session manifest;
- a trade signal precedes first Top-20 discovery;
- outcome labels influence ranking construction;
- final replay performs network fetches;
- research baseline differs from frozen v1.2;
- cache/data failures are silently discarded; or
- v1.2 source/policy constants are changed during the run.

## Decision after the experiment

Only after chronological validation should a separate v1.3 proposal decide
whether evidence supports any combination of:

- controlled-pullback-only authority;
- one-trade-per-symbol authority;
- a new causal leaderboard-trajectory qualification layer; or
- retaining v1.2 unchanged.

Do not implement those production changes as part of the research replay.
