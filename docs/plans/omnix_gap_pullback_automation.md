# Omnix gap-pullback automation

## Thesis

**Don't predict the bottom. Detect a failed continuation downward, prove that detection is causal, and only trade it when realistic execution still leaves positive expectancy.**

The target setup is a volatile overnight gapper that establishes an opening impulse, sells off, then demonstrates that sellers have failed to continue the move lower. The automated strategy is deliberately narrower than “buy a dip”:

`gap / opening impulse → L1 first confirmed pullback low → B1 confirmed bounce high → L2 confirmed higher low → contracting sell volume → regular-session VWAP reclaim → B1 break → breakout-volume confirmation → optional break/hold confirmation`

A signal is not valid until L2 is confirmed. Pivot confirmation uses configured right-side bars; the system never labels a pivot at a time when those bars did not yet exist.

## Strategy catalog and versioning

Automated strategies are treated as named, versioned strategy definitions rather than one-off terminal behavior. The current catalog contains `gap_pullback_v1`; the Trading UI consumes a strategy definition/phase catalog so additional strategies can add their own configuration editor, research workflow and phases without redefining the paper engine.

`gap_pullback_v1` supports two persisted configuration versions:

- **1.0.0** preserves the earlier permissive defaults so existing saved configurations and historical tests remain reproducible.
- **1.1.0** is the strict failed-selloff profile created by the current UI. Every threshold is persisted and editable; the defaults are a starting research hypothesis, not a claim that those values are optimal.

The v1.1 UI baseline is:

- gap `>= 20%`;
- price `$0.50–$20`;
- premarket dollar volume `>= $10M`;
- time-of-day relative volume `>= 5x`;
- preferred float `2M–30M` shares, scored by default and optionally hard-required;
- maximum spread `150 bps`;
- timestamped catalyst evidence required;
- deterministic rejection of configured serious supply flags (`registered_offering`, `atm`, `warrants`, `convertible`, `equity_line` by default);
- opening impulse `>= 8%`;
- pullback depth `15–55%` of the impulse range;
- average red-bar pullback volume no more than `70%` of opening-impulse average volume;
- confirmed higher low;
- regular-session VWAP reclaim;
- break of the confirmed B1/lower high;
- breakout volume `>= 1.25x` recent average;
- one-bar break-and-hold/retest by default, with a `25 bps` B1 tolerance;
- minimum deterministic quality score `7/10`;
- stop below L2 with a configurable buffer and default `2R` target.

All of those values, plus pivot widths, volume lookback, time window and server risk controls, are visible and editable in the Strategies workspace.

## Safety boundary

The implementation has three execution modes only:

- `off`: no strategy evaluation/execution work beyond persisted configuration.
- `shadow`: evaluate and persist deterministic state/reason evidence, but create no orders.
- `auto_paper`: submit only to Omnix paper trading after deterministic strategy, execution-data and server-risk gates pass.

There is no live-broker mode. AI catalyst classification and statistical model scores are shadow-only and are intentionally absent from `strategy_monitor.py`. The UI can use LLM research to suggest candidate exclusions, but applying those suggestions changes only the operator's selection. A new immutable narrowed universe must be explicitly frozen before that choice affects deterministic evaluation.

## Daily phased workflow

The Strategies UI exposes the complete daily workflow as six visible phases rather than hiding automation behind one on/off switch:

1. **Scan & freeze** — perform current-only configured gapper discovery. Finviz Top Gainers is supported as a source-ranked morning cohort with independent Yahoo enrichment; legacy Yahoo Day Gainers remains available. Freeze the raw point-in-time population, including eventual fades/failures.
2. **Research & narrow** — collect timestamped catalyst evidence, inspect float/liquidity/spread/supply flags, supplement Yahoo headline evidence with SEC/company evidence when available, and explicitly select candidates to retain.
3. **LLM research** — optionally classify only the stored evidence. Results are cited, persisted as research events and remain shadow-only.
4. **Deterministic setup** — monitor the failed-selloff state machine and expose each candidate's current state/reason, including volume contraction, L1/B1/L2, VWAP, breakout and hold confirmation.
5. **Daily selection** — only candidates that pass all mandatory hard gates and the configured quality threshold can reach `entry_ready`; the operator can freeze a smaller daily universe before arming automation.
6. **AUTO PAPER** — apply server risk, authoritative Alpaca IEX execution evidence, deterministic paper fills, persisted protection and end-of-day flattening.

The candidate workbench shows gap, price, TOD RVOL, dollar volume, float, spread, catalyst evidence count, deterministic supply flags, LLM research result, latest deterministic state/reason and quality score. For configurations with intraday learning enabled it also shows the latest research-only dynamic rank/pattern plus squeeze, failed-selloff, trend and gap-retention scores. The current universe JSON remains inspectable for provenance and external evidence integration.

## Point-in-time catalyst research

`POST /api/trading/strategies/{strategy_id}/research/capture-yahoo` provides a current-only research step for the attached universe. It queries Yahoo search/news for recent candidate headlines, stores each accepted headline as immutable timestamped `CatalystEvidence`, merges deterministic supply flags found in the evidence, freezes a **new** research universe and updates the paused/shadow strategy to that new universe.

This route deliberately refuses to mutate a strategy while it is in `auto_paper`; the operator must pause automation before changing the day's research universe. Yahoo headline evidence is a starting point, not a complete filing review. Existing catalyst APIs remain available for SEC/company/news/manual evidence, and the UI's evidence JSON makes those immutable IDs visible and auditable.

Yahoo catalyst capture is current-only. A later search cannot be used to reconstruct a historical catalyst set, because that would introduce look-ahead/survivorship bias. Historical research must reuse the exact frozen evidence/universe captured at the time.

## Quality score: ranking without weakening hard gates

The deterministic strategy exposes a transparent ten-point score:

| Category | Points |
| --- | ---: |
| Fresh timestamped catalyst evidence | 0–2 |
| Supply/float profile | 0–2 |
| Opening structure | 0–2 |
| Controlled low-volume pullback | 0–2 |
| VWAP reclaim + B1 break + hold | 0–2 |

The default minimum is `7/10`, but the score is **not** a substitute for mandatory structure. A candidate still making lower lows, failing VWAP/B1, showing excessive sell volume, carrying a configured severe dilution flag, or failing another hard gate cannot compensate by scoring well elsewhere.

## Data-source boundary

US-equity research and execution deliberately use different providers:

- **Finviz Top Gainers** can supply the ordered point-in-time morning discovery cohort for the learning experiment; it never supplies execution evidence.
- **Yahoo** supplies independent chart/history/current-price enrichment and current-only headline research. Legacy Yahoo Day Gainers discovery remains available for the canonical V2 cohort. Yahoo can never authorize a paper fill.
- **Alpaca IEX** supplies the authoritative real-time bid/ask/trade observation for US-equity paper execution. IEX is explicitly recorded as a **partial-market** feed and is never described as consolidated SIP/NBBO coverage.
- If Alpaca credentials are missing, a quote is stale/future-dated/bookless/over-wide, the recurring US-equity calendar says the session is closed, or provider trading-status evidence says the symbol is halted, execution fails closed.

The provider identity is retained with execution evidence so future IEX-vs-SIP comparisons can quantify feed effects rather than assuming equivalence.

## P0 — execution correctness

### Execution-data contract

`ExecutionObservation` separates chart/research prices from execution evidence. Paper execution records source timestamp, receipt timestamp, session, bid/ask, displayed sizes, latest trade, optional current-minute range/volume, freshness class, halt evidence and explicit eligibility.

Execution rejects:

- stale observations;
- source timestamps beyond the allowed future clock-skew tolerance;
- missing bid/ask;
- excessive spread;
- cached/fallback/unknown freshness;
- closed recurring US-equity sessions, including standard holidays and early closes;
- a known provider trading halt.

Unscheduled exchange closures remain provider-status events. Loss of the optional status stream never turns unknown status into a positive “not halted” assertion; a previously known halt remains fail-closed until resume evidence is observed.

Yahoo remains research/diagnostic only. `ProviderRegistry` overlays an equity Yahoo/Stooq chart binding onto the corresponding Alpaca IEX execution binding while preserving the requested persisted binding ID for existing paper orders.

### Paper execution v2

`paper-execution-v2` is the shared deterministic fill policy used by paper monitoring and the gap-pullback portfolio backtester. It models:

- bid/ask-side market pricing;
- deterministic slippage;
- worse-price stop gap-through behavior;
- observation latency;
- stale and halted-market rejection;
- maximum liquidity participation;
- partial fills;
- commissions and transactional ledger/position/order updates.

**Liquidity is not inferred from cumulative daily volume.** Live Alpaca observations prefer side-specific displayed top-of-book size (`ask_size` for buys, `bid_size` for sells). Historical observations fall back to the individual bar's volume. This prevents a million-share daily total from being treated as immediately executable size.

Caller `reference_price` is reservation evidence only. Browser observations are non-authoritative and cannot produce fills.

### Shared protection semantics

Manual paper protection, automated strategy protection and historical backtesting use the same pessimistic stop-before-target trigger helper. A minute range is trusted only when its bar started at or after the position/protection activation time; this prevents a pre-entry low/high in the same minute from being misclassified as a post-entry stop/target touch.

Manual paper take-profit/stop-loss state is persisted in PostgreSQL, not `localStorage`. The paper monitor implements OCO-style first-trigger behavior. Strategy entries have separate persisted strategy protections so automated stop/target/force-flat state survives browser reloads.

### Server-authoritative risk

Server strategy risk includes risk per trade, daily loss, open risk, max positions, max trades/day, max notional, one trade/symbol/day, spread, entry window, force-flat time and kill switch. Reset/archive operations cancel protection and turn related strategy automation off.

## P1 — deterministic research, discovery and backtesting

### Point-in-time Yahoo gapper discovery

`POST /api/trading/strategies/universes/discover-yahoo` performs **current-only** Yahoo top-gainer discovery and immediately freezes the result. The server rejects attempts to use this route as a historical screener reconstruction because doing so later would introduce hindsight/survivorship bias.

For each qualifying listed equity, the discovery path records the observation time and computes point-in-time evidence including normalized previous close, observed premarket/current price, gap %, premarket volume/dollar volume, time-of-day relative volume, spread when available, market cap/float when available and discovery rank. Time-of-day RVOL compares the current cumulative volume only with historical sessions truncated at the same New York clock minute.

Missing secondary evidence does not silently remove a candidate. The candidate is retained and the deterministic strategy can reject it explicitly (for example `TOD_RVOL_MISSING`). This preserves eventual failures/fades in the denominator.

### Immutable universe provenance

`GapperUniverseSnapshot` is immutable and fingerprinted. Candidate snapshots may carry `observed_at` plus field-level `evidence_observed_at` timestamps. Provider/scanner freezes require a candidate observation timestamp, and any candidate evidence occurring after `evaluation_time` is rejected.

If a candidate cites catalyst evidence IDs, the strategy API resolves those immutable records and rejects a freeze/backtest when either publication or capture occurred after the universe evaluation time. Direct immutable-universe uploads are re-fingerprinted by the server before persistence.

Manual/imported candidate JSON remains supported for externally captured datasets, but historical tests must reuse the exact frozen universe rather than reconstructing one from later winners.

### Causal gap_pullback_v1

The strategy runs on finalized one-minute regular-session bars. Regular-session VWAP resets at 09:30 America/New_York. Confirmed pivots require both left and right bars. The implementation exposes deterministic state and reason codes rather than an opaque score.

The v1.1 evaluator additionally compares average red-bar volume during the selloff with average opening-impulse volume and can require a causal post-break hold/retest before `entry_ready`.

The causality gate is **prefix invariance**: evaluation results for any historical prefix must be identical regardless of bars appended later. Tests also verify that L1 is not visible until its required right-side confirmation exists.

### Portfolio backtest and paper parity

A morning gapper strategy selects among multiple simultaneous candidates, so backtesting is session/portfolio based rather than only single-symbol. Frozen session datasets include the universe and per-symbol bars in one fingerprint. Entry uses the next bar after the trigger.

Parity is defined across the full decision path, not merely by calling the same fill helper:

`signal → chronological candidate arbitration → server risk sizing → execution observation → paper_fill_decision → shared protection trigger → exit fill`

Backtests therefore:

- use `paper-execution-v2` / `paper_fill_decision`;
- call the same `size_strategy_entry` server-risk function as AUTO PAPER;
- track virtual account cash/equity, realized daily PnL, open risk and open positions;
- use `(entry_time, discovery_rank, instrument_id)` as the deterministic simultaneous-trigger tie-break, matching the frozen universe priority;
- rerun the fill engine with the actual risk-sized quantity so liquidity/partial-fill effects apply to the requested trade size;
- use the same pessimistic stop-before-target trigger helper as paper monitors.

Reported evidence includes trigger/trade counts, risk-rejection reasons, R multiple, expectancy, approximate 95% expectancy interval, profit factor, MFE, MAE, hold duration, slippage and candidate-to-trigger conversion. Walk-forward split support separates sequential training/test sessions.

Replay gap validation is session aware: normal overnight/weekend exchange closures are not reported as missing intraday bars, while missing bars inside one continuous session are.

## P2 — automated paper runner and terminal

The gateway owns a deterministic strategy monitor with bounded polling and environment controls. The runner loads active configurations and the attached frozen universe, evaluates each candidate, checks Alpaca IEX execution eligibility, applies server risk, creates idempotent paper orders, persists state/rejection events and reconciles server stop/target protection.

The Strategies workspace provides:

- an extensible strategy catalog and named strategy instances;
- the six visible daily pipeline phases;
- complete `gap_pullback_v1` configuration and strict v1.1 baseline loading;
- strategy mode/account/universe selection;
- server risk controls and kill switch;
- current Yahoo gapper scan/freeze;
- current Yahoo catalyst headline capture and immutable research-universe rollover;
- point-in-time universe JSON/evidence inspection;
- optional LLM evidence review with explicit shadow-only labeling;
- candidate include/exclude selection and “freeze selected” daily narrowing;
- candidate state/rejection/quality-score visibility;
- active server protection visibility;
- explicit paper-only and no-live-broker safety messaging.

The compact Trading header keeps the Scanner/Backtest/Strategies/Trade/AI Research tool group visible rather than hiding automated strategy access behind an invisible horizontal-scroll area.

## P3 — catalyst evidence and AI shadow classification

Catalyst context is stored as timestamped immutable evidence, not an ungrounded LLM opinion. Evidence carries source type/locator, publication/capture timestamps, text hash, structured facts, deterministic dilution flags and an immutable fingerprint.

The shadow classifier receives only selected stored evidence and must cite exactly those evidence IDs in its structured output. Classification includes catalyst class, directional bias, novelty, dilution risk and confidence. `shadow_only=true` is enforced by contract. The deterministic strategy does not consume this output.

Yahoo headline capture supplies a current-only baseline research source. SEC/company/manual evidence remains supported through the catalyst evidence API and should be preferred when a filing/supply question requires primary evidence. Source acquisition remains separated from the evidence boundary so future adapters can respect licensing and credentials without weakening immutability or causality.

## P4 — statistical bounce model

The model label is `P(+2R before -1R within 90 minutes)`. Same-bar stop/target ambiguity resolves pessimistically to the stop.

The feature contract includes gap %, premarket dollar volume, TOD RVOL, float/market cap logs, spread, opening impulse, HOD distance, pullback depth/volume, L2/L1, VWAP distance/slope, breakout volume, ATR %, time since open, catalyst flags and dilution evidence.

A transparent standardized logistic-regression fitter produces persisted versioned artifacts containing coefficients, intercept, normalization statistics, training metadata, log loss and an immutable fingerprint. Model versions cannot be silently overwritten with different payloads. Scores remain shadow-only.

`POST /api/trading/models/bounce/validate-shadow` evaluates a locked model on dated out-of-sample examples and reports:

- OOS log loss;
- base-rate log loss and improvement;
- Brier score;
- calibration bins and expected calibration error;
- independent session count and example count;
- an explicit evidence-volume sufficiency flag.

Default evidence-volume thresholds are 100 labeled OOS examples across at least 20 sessions. Meeting those counts is **not** proof of profitability; it only means the sample is large enough to start interpreting OOS metrics. A boosted-tree model remains deliberately deferred until the transparent baseline has enough frozen OOS evidence to justify added complexity.

## Release gates

1. **Execution correctness:** caller/reference prices cannot fill; stale/future-dated/unavailable/ineligible data fails closed; spread/slippage/stop-gap/latency/liquidity/partial-fill behavior is deterministic.
2. **Feed correctness:** Yahoo cannot authorize fills; Alpaca IEX is recorded as partial-market evidence; displayed book size rather than daily cumulative volume controls live participation; known halts reject execution.
3. **Session correctness:** recurring US-equity holidays/early closes and extended-session boundaries classify deterministically; provider status handles symbol-specific halts and exceptional status events.
4. **Strategy causality:** right-side pivot confirmation and prefix invariance pass; v1.1 pullback-volume and hold confirmation operate only on observable prefixes.
5. **Backtest/paper parity:** both use the shared risk-sizing, fill and protection-trigger policies, with deterministic chronological candidate arbitration.
6. **Point-in-time research:** provider/scanner universes have observation timestamps; Yahoo scan/headline capture is current-only; future candidate/catalyst evidence is rejected; historical tests reuse frozen universes/evidence.
7. **Automated paper only:** strategy monitor has no broker order adapter and no AI/model execution dependency.
8. **AI/model shadow:** catalyst and model results remain evaluative; LLM exclusions require an explicit immutable universe-selection step before deterministic evaluation.
9. **Lifecycle safety:** resetting or archiving a paper account disables associated automation and cancels protection state.
10. **Operational data:** Alpaca IEX credentials must be configured for US-equity AUTO PAPER. IEX remains a partial-market paper-execution source; no result may be presented as SIP/NBBO or live-fill equivalence.
11. **Evidence before promotion:** parameter changes are locked before OOS evaluation; sequential walk-forward evidence, expectancy uncertainty and adverse spread/slippage/latency stress cases must be reviewed before any future promotion beyond experimental paper use.
12. **Strategy UI auditability:** every execution-authorizing v1.1 parameter, daily pipeline phase, candidate decision/rejection, quality score and active protection is inspectable in the Trading Strategies workspace.

Paper or historical results are research evidence, not a profitability guarantee.


## Completion and correctness amendments — 2026-08-24

The production strategy catalog now contains persisted `1.0.0`, strict `1.1.0`, reviewed-research-policy `1.2.0`, and frozen prospective `2.0.0` semantics. `2.0.0` remains promotion-gated by prospective SHADOW evidence and explicit operator review.

Final roadmap hardening makes the following contracts release requirements rather than dashboard-only diagnostics:

- **Exit parity:** AUTO PAPER and the portfolio backtester both evaluate the configured causal RSI cross in addition to shared stop/target semantics. V2 retains its separately versioned profit-protection and max-hold rules.
- **Immutable initial risk:** strategy protections retain the original stop/target geometry even after a V2 protected stop moves. Canonical paper R is computed from that original risk, not the final moved stop.
- **Prospective excursions:** AUTO PAPER protections persist favorable/adverse price extrema so completed round trips retain MAE/MFE in R.
- **Typed supply state:** keyword matches alone are not execution-authoritative dilution vetoes. Supply evidence is classified as active, terminated, exhausted, expired, redeemed, withdrawn, or unknown; only a resolved active state becomes a deterministic `dilution_flag`. Unknown/inactive states remain research evidence.
- **Soft archive:** normal strategy removal is an archive operation (`mode=off`, disabled, immutable `archived_at`). Runs/events/protections remain first-class queryable evidence; hard database deletion is no longer the operator workflow.
- **Dashboard regime separation:** SHADOW replay and AUTO PAPER performance are selected separately and compared explicitly. They are not pooled into the default expectancy statistic. Lifecycle funnels count one profile/session/universe/instrument lifecycle and advance only on proven deterministic stages.
- **Risk history:** equity/risk snapshots are emitted when protection state or stop levels change, not only when balances/positions mutate.

The paper strategy dashboard is therefore an evidence console for prospective promotion and implementation-loss measurement; it is not a generic brokerage performance screen and historical/reconstructed results remain research evidence rather than a profitability guarantee.


## Finviz intraday learning extension

The Finviz learning loop is documented in `docs/trading/FINVIZ_INTRADAY_LEARNING_LOOP.md`.

It is an observational layer over the frozen morning population:

- the source cohort is captured once before the open rather than re-scraped after winners emerge;
- every finalized one-minute regular-session prefix can update research-only dynamic scores;
- learning events do not alter deterministic strategy state or authorize orders;
- the canonical Yahoo-backed V2 qualification fingerprint remains isolated from a Finviz V2 learning experiment, so historical Yahoo evidence cannot promote the new cohort.
- deterministic learning evaluates the full frozen cohort every finalized minute, while the default LLM is event-driven: material state/rank/VWAP/turnover/score changes trigger analysis, quiet top names receive a 10-minute heartbeat during the entry window, and `entry_ready` is always included;
- normal LLM batches default to five active names, use compact deltas plus the previous thesis, receive a periodic 30-minute full-context refresh, and are capped at one ordinary call per five minutes (with `entry_ready` allowed to bypass the cooldown);
- runtime counters and batch events expose provider-reported input/output/total token usage when available, with a labeled character/4 estimate fallback, so token cost can be measured prospectively rather than guessed.
