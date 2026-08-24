# Deep-recovery candidate census protocol

Status: **COMPLETED — DESCRIPTIVE DEVELOPMENT RESULT ONLY**

This protocol answers a descriptive question over the existing immutable development cache: which morning gap candidates experienced a meaningful post-open selloff and then recovered at least 30% from a subsequently observed trough?

It is research-only. It does not change frozen V2, does not authorize AUTO PAPER, does not call a market-data provider, and does not read the March holdout.

## Data block

- Development sessions: 2025-10-01 through 2026-02-27.
- Input: the existing immutable 103-session causal cache used by the prior V3 development studies.
- Coverage: 103/103 sessions, 102 dataset sessions, one true no-candidate session, 447 candidate/day observations.
- Source fidelity remains reconstructed Alpaca IEX partial-market evidence with active-listing/survivorship caveats.
- March was not loaded by this census.

## Frozen recovery definition

All measurements use finalized regular-session 1-minute bars only.

1. **Opening anchor:** the first 15 regular-session minutes, 09:30 through 09:44 ET. The opening high is the first bar attaining the maximum high in that window.
2. **Post-opening trough:** after the opening-high bar, maintain the running minimum low. A recovery path is considered only once that running low is at least 5% below the opening high. This 5% floor exists only to distinguish a genuine selloff/recovery sequence from a straight continuation or trivial dip.
3. **Absolute recovery:** on each later finalized bar, `bar.high / running_low - 1`. The maximum value is the candidate's maximum trough-to-later-peak recovery. The user's threshold is **>=30% absolute recovery**.
4. **Selloff retracement:** for the same selected low/high pair, `(later_high - running_low) / (opening_high - running_low)`. This is reported separately so "30% recovery" can also be inspected as percentage of the selloff retraced; it is not the primary qualification rule.
5. **Actionable recovery:** the maximum qualifying sequence using bars whose end time is no later than 11:30 ET, matching frozen V2's entry horizon.
6. **Full-session recovery:** the same sequence through the regular-session close. This identifies strong recoveries that occur too late for the current entry window.
7. Sequence order is mandatory: opening high -> later running low -> later high. A future low cannot be paired with an earlier high. A bar that establishes a new trough cannot use that same bar's high as a post-trough recovery peak because 1-minute OHLC does not reveal intrabar ordering.

The census records both the best actionable and best full-session path, including opening-high time/price, trough time/price, later-peak time/price, selloff depth, absolute recovery and selloff retracement.

## Frozen-V2 miss attribution

For every candidate/day row, replay the unmodified frozen V2 strategy on the same immutable session and record its candidate decision:

- final state;
- rejection reason;
- whether a structural trigger occurred;
- whether a trade was selected.

The primary diagnostic is the distribution of frozen-V2 states/rejection reasons among candidates with >=30% actionable recovery, followed by candidates with >=30% full-session recovery only.

## Completed census result

The provider-free census found **90 of 447 candidates (20.1%)** with a >=30% absolute recovery observable by 11:30 ET. That does not mean 90 candidates should be admitted to the strategy. **77 of the 90 failed frozen-V2 hard liquidity/data gates**: 39 had missing TOD RVOL, 35 had insufficient premarket dollar volume, and 3 had TOD RVOL below the frozen floor.

Only **13 candidate/session cases** both recovered >=30% by 11:30 and passed the frozen-V2 hard gates. Frozen V2 traded only one of them. The other 12 were missed primarily by structural/timing geometry rather than liquidity:

| Session | Symbol | Frozen-V2 outcome |
|---|---|---|
| 2025-10-03 | DFLI | `V2_RESOLUTION_TOO_SLOW` |
| 2025-10-13 | ELBM | `ENTRY_WINDOW_CLOSED` |
| 2025-10-15 | DFLI | traded |
| 2025-10-20 | BYND | `V2_BASE_TOO_FAST` |
| 2025-10-24 | MEDS | `ENTRY_WINDOW_CLOSED` |
| 2025-11-03 | TGE | `V2_RESOLUTION_TOO_SLOW` |
| 2025-11-28 | KTTA | `ENTRY_WINDOW_CLOSED` |
| 2025-12-04 | KALA | `V2_BASE_TOO_FAST` |
| 2026-01-12 | AZIO | `V2_BASE_TOO_FAST` |
| 2026-01-26 | NAMM | `V2_RESOLUTION_TOO_SLOW` |
| 2026-01-28 | FEED | `SECOND_LOW_NOT_HIGHER` |
| 2026-01-30 | CISS | `V2_BASE_TOO_FAST` |
| 2026-02-03 | GXAI | `ENTRY_WINDOW_CLOSED` |

This result supports a **parallel strong-recovery continuation hypothesis** while retaining the same hard candidate gates. It does not support weakening the liquidity/data floors to include the 77 eventual bouncers that failed them.

Census evidence: workflow run `32666857501`, artifact `9500269010`, digest `sha256:8f320e68bfa635d528834f8af49f19b55bbdf782c804870cbceb59c73c1d669e`.

## Outputs

The completed run emitted:

- `candidate_recovery.csv`: one row for every candidate/day observation in the development cache;
- `recovery_30_actionable.csv`: >=30% recovery observable by 11:30 ET;
- `recovery_30_full_session.csv`: >=30% recovery at any regular-session time;
- `results.json`: coverage, counts, recovery-rate summaries, frozen-V2 miss attribution and dataset fingerprints;
- `summary.md`: human-readable checkpoint.

The all-candidate CSV includes original candidate fields needed for interpretation: gap %, premarket price, premarket dollar volume, TOD RVOL, spread, discovery rank and the frozen-V2 decision fields.

## Interpretation rules

- Eventual recovery is an outcome label. It **must not** be used to authorize an earlier trade as if the future recovery were known.
- The census may be used to formulate a new causal successor setup after the result is observed, but any rule derived from these development outcomes is in-sample and requires untouched/prospective validation before execution authority.
- Frozen V2 remains unchanged regardless of the census result.
- No parameter sweep of the 30% threshold, opening window, 5% meaningful-selloff floor or 11:30 cutoff is permitted on this development result.
