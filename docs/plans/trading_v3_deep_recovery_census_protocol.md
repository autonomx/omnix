# Deep-recovery candidate census protocol

Status: **FROZEN BEFORE DEVELOPMENT CENSUS**

This protocol answers a descriptive question over the existing immutable development cache: which morning gap candidates experienced a meaningful post-open selloff and then recovered at least 30% from a subsequently observed trough?

It is research-only. It does not change frozen V2, does not authorize AUTO PAPER, does not call a market-data provider, and does not read the March holdout.

## Data block

- Development sessions: 2025-10-01 through 2026-02-27.
- Input: the existing immutable 103-session causal cache used by the prior V3 development studies.
- Expected coverage: 103/103 sessions, 102 dataset sessions, one true no-candidate session, 447 candidate/day observations.
- Source fidelity remains reconstructed Alpaca IEX partial-market evidence with active-listing/survivorship caveats.
- March is not loaded by this census.

## Frozen recovery definition

All measurements use finalized regular-session 1-minute bars only.

1. **Opening anchor:** the first 15 regular-session minutes, 09:30 through 09:44 ET. The opening high is the first bar attaining the maximum high in that window.
2. **Post-opening trough:** after the opening-high bar, maintain the running minimum low. A recovery path is considered only once that running low is at least 5% below the opening high. This 5% floor exists only to distinguish a genuine selloff/recovery sequence from a straight continuation or trivial dip.
3. **Absolute recovery:** on each later finalized bar, `bar.high / running_low - 1`. The maximum value is the candidate's maximum trough-to-later-peak recovery. The user's threshold is **>=30% absolute recovery**.
4. **Selloff retracement:** for the same selected low/high pair, `(later_high - running_low) / (opening_high - running_low)`. This is reported separately so "30% recovery" can also be inspected as percentage of the selloff retraced; it is not the primary qualification rule.
5. **Actionable recovery:** the maximum qualifying sequence using bars whose end time is no later than 11:30 ET, matching frozen V2's entry horizon.
6. **Full-session recovery:** the same sequence through the regular-session close. This identifies strong recoveries that occur too late for the current entry window.
7. Sequence order is mandatory: opening high -> later running low -> later high. A future low cannot be paired with an earlier high.

The census records both the best actionable and best full-session path, including opening-high time/price, trough time/price, later-peak time/price, selloff depth, absolute recovery and selloff retracement.

## Frozen-V2 miss attribution

For every candidate/day row, replay the unmodified frozen V2 strategy on the same immutable session and record its candidate decision:

- final state;
- rejection reason;
- whether a structural trigger occurred;
- whether a trade was selected.

The primary diagnostic is the distribution of frozen-V2 states/rejection reasons among candidates with >=30% actionable recovery, followed by candidates with >=30% full-session recovery only.

## Outputs

The run must emit:

- `candidate_recovery.csv`: one row for every candidate/day observation in the development cache;
- `recovery_30_actionable.csv`: >=30% recovery observable by 11:30 ET;
- `recovery_30_full_session.csv`: >=30% recovery at any regular-session time;
- `results.json`: coverage, counts, recovery-rate summaries, frozen-V2 miss attribution and dataset fingerprints;
- `summary.md`: human-readable checkpoint.

The all-candidate CSV must include original candidate fields needed for interpretation: gap %, premarket price, premarket dollar volume, TOD RVOL, spread, discovery rank and the frozen-V2 decision fields.

## Interpretation rules

- Eventual recovery is an outcome label. It **must not** be used to authorize an earlier trade as if the future recovery were known.
- The census may be used to formulate a new causal successor setup after the result is observed, but any rule derived from these development outcomes is in-sample and requires untouched/prospective validation before execution authority.
- Frozen V2 remains unchanged regardless of the census result.
- No parameter sweep of the 30% threshold, opening window, 5% meaningful-selloff floor or 11:30 cutoff is permitted in this run.
