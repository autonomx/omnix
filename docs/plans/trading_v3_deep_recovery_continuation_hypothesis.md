# V3 deep-recovery continuation feasibility hypothesis

Status: **PROSPECTIVE SHADOW COLLECTION APPROVED — NO EXECUTION AUTHORITY**

This hypothesis was formulated after the frozen deep-recovery census identified a distinct family of liquid candidates that recovered >=30% by 11:30 ET but were usually missed by frozen V2's L1 -> B1 -> L2 timing geometry. It is therefore not an independent validation. The development replay answered only whether the causal implementation was mechanically/trading-economically plausible enough to justify prospective SHADOW collection.

Frozen V2 remains unchanged. March remains sealed.

## Motivation from the frozen census

The predeclared census reviewed every development candidate/day observation. The update direction is intentionally narrow:

- **retain frozen V2's hard universe/liquidity gates**;
- do **not** admit candidates merely because they later bounced;
- add a parallel continuation shape for strong V-shaped / slower-resolving recoveries that do not satisfy V2's exact L1/B1/L2 timing ownership.

## Causal feasibility rule

The evaluator sees finalized 1-minute prefixes only.

1. Apply the same frozen-V2 hard candidate gates: gap, price, premarket dollar volume, TOD RVOL, spread, catalyst/supply settings and float mode.
2. Wait until the first 15 regular-session minutes are finalized. Freeze the first attained maximum high from 09:30 through 09:44 ET as `opening_high`.
3. After that opening-high bar, maintain a causal running low. The setup is inactive until the running low is at least **5% below opening_high**.
4. The strong-recovery threshold is not anticipated. A signal is possible only when a **finalized close is >=30% above the already-observed running low**.
5. Require the signal close to be above regular-session VWAP.
6. Require the signal close to break the **highest high of the prior three finalized 1-minute bars**. This prevents a 30% recovery reading from authorizing an entry while price is already rolling over.
7. Signal time must be between 09:45 and frozen V2's 11:30 ET last-entry cutoff.
8. The research stop is **15 bps below the minimum low of the latest five finalized 1-minute bars including the signal bar**. This deliberately does not use the original deep trough as the stop; doing so would create an impractically wide risk distance after a 30% rebound.
9. Historical feasibility entered on the next eligible 1-minute execution bar and reused deterministic portfolio/risk sizing.
10. For comparability, historical feasibility retained frozen V2 management: 1.5R target, +0.75R profit-protection trigger, protected stop +0.25R, 60-minute maximum hold and end-of-day controls.

No EMA/MACD/Stoch-RSI gate was added in the historical feasibility pass so entry-shape effects remained isolated and the known historical warm-up limitation was not turned into another confound.

## Completed development feasibility result

Coverage was **103/103 sessions** from 2025-10-01 through 2026-02-27 using the immutable cached reconstruction. Provider calls were zero. March was not loaded and frozen V2 was unchanged.

The exact parallel recovery rule produced:

- **10 trades**;
- **7 winners / 3 losers**;
- expectancy **+0.082070R**;
- one-sided 90% lower confidence bound **-0.296606R**;
- maximum drawdown **2.084568R**;
- net P&L **+$249.59** on the research replay;
- only **one** instrument/session overlap with frozen V2 (`DFLI|2025-10-15`).

The ten historical feasibility entries were DFLI (2025-10-03), ELBM, DFLI (2025-10-15), BYND, MEDS, TGE, AZIO, FEED, CISS and GXAI. Of the 13 hard-gate-qualified >=30% recovery cases from the census, the exact rule deliberately did not force entries in **KTTA (2025-11-28), KALA (2025-12-04), and NAMM (2026-01-26)** because the predeclared causal confirmation was not completed in time. Those misses are retained as misses rather than used to loosen the same-sample rule.

The result is mechanically plausible but **does not establish a reliable edge**: expectancy is small and the lower confidence bound remains negative. It therefore supports only prospective SHADOW collection, not AUTO PAPER or a V2 modification.

Corrected feasibility evidence: workflow run `32667292467`, artifact `9500390532`, digest `sha256:76c8f4e88ed4e1a1877f3a70266277ce2d629ad63e6009fd23df94223b48628f`.

## Prospective implementation boundary

The rule is implemented as research setup `deep_recovery_continuation_v1`, rule version `1.0.0-shadow`.

- The collector runs only beside enabled `2.0.0` strategies in **SHADOW** mode.
- It reuses frozen V2 hard candidate gates but does not alter the frozen V2 state machine or fingerprint.
- It persists transition-only recovery research states and one first signal per symbol/session.
- On a signal it may capture the same execution-observation/prospective-feature evidence used by V2 SHADOW.
- `execution_authority` is always false.
- The monitor has no paper repository, `PaperOrderRequest`, `place_order`, protection, or live-broker dependency.
- Deep-recovery events are isolated from the normal V2 activity feed so a recovery research state cannot masquerade as V2 `entry_ready`.

The next decision point is after an untouched/prospective sample exists. Any future qualification policy must be predeclared before inspecting that prospective outcome set.

## No same-sample rescue

Do not sweep the 30% threshold, 5% selloff floor, 3-bar breakout, 5-bar stop, 09:45 opening anchor or exit parameters after seeing the result. Do not alter V2 to absorb historical recovery misses. Further changes require prospective evidence or a separately predeclared future hypothesis.
