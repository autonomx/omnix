# Deep-recovery continuation prospective qualification policy

Status: **FROZEN BEFORE PROSPECTIVE OUTCOMES — SHADOW ONLY**

Setup: `deep_recovery_continuation_v1`

Rule version: `1.0.0-shadow`

Prospective epoch: **2026-08-24 onward**

This policy is frozen before the first prospective session for the deep-recovery continuation setup. Historical development feasibility cannot satisfy any item in this policy and must never be mixed into the prospective sample.

## Strategy definition under qualification

A qualifying signal must be produced by the exact research rule already implemented and documented:

- frozen-V2 hard candidate gates;
- finalized 1-minute bars only;
- opening anchor 09:30-09:44 ET;
- >=5% post-opening selloff;
- finalized close >=30% above an already-observed running low;
- close above regular-session VWAP;
- close above the highest high of the prior three finalized 1-minute bars;
- signal no later than 11:30 ET;
- research stop 15 bps below the lowest low of the latest five finalized bars;
- one first signal per symbol/session.

Any change to those rules, to the hard candidate gates, or to the outcome-management assumptions creates a new hypothesis/version and starts a new prospective epoch. It must not inherit this evidence.

## Required evidence integrity

Only live/prospective `deep_recovery_shadow` events from the epoch may count. Each counted signal must have:

1. the exact setup/rule version;
2. `execution_authority=false`;
3. an immutable frozen morning universe / candidate provenance;
4. the frozen V2 profile fingerprint used for hard-gate evaluation;
5. causal signal features computed only from finalized bars available at signal time;
6. an execution observation captured at/after the signal, with its eligibility status and prospective-feature fingerprint retained;
7. a deterministic post-session outcome reconstructed from point-in-time market data without future data affecting entry eligibility.

Signals with missing or unverifiable provenance remain visible but do not count as matched qualification trades.

## Frozen quantitative floors

All floors must pass simultaneously:

- **matched eligible trades >= 20**;
- **distinct sessions >= 15**;
- **distinct symbols >= 10**;
- **execution-evidence match rate >= 90%**;
- **expectancy >= +0.20R**;
- **one-sided 90% lower confidence bound > 0R**;
- **maximum drawdown <= 5R**.

R must be anchored to the causal signal/fill and the predeclared structural research stop. Outcome handling must be fixed before outcomes are scored. No alternate stop/target/timeout may be selected after observing the prospective results.

## Promotion boundary

Passing the floors does **not** grant order authority. It means only that this exact setup is quantitatively eligible for a separate reviewed promotion proposal.

Before any execution-authorizing implementation:

- inspect the full prospective trade list and data-quality exceptions;
- verify no setup/version drift;
- verify no hidden concentration in one symbol/session/regime;
- record an explicit operator review bound to the exact evidence fingerprint;
- create a separately versioned deterministic execution strategy or strategy-family configuration;
- keep the LLM/Hermes path research-only and outside order authorization.

Until all of those steps exist and pass, `deep_recovery_continuation_v1` remains SHADOW-only regardless of its observed P&L.

## Anti-overfitting rules

- Do not lower the 30% recovery threshold, 5% selloff floor, 3-bar breakout, or 5-bar stop after seeing prospective misses.
- Do not extend the 11:30 entry cutoff because a later candidate recovered.
- Do not weaken liquidity/data hard gates because an eventual recovery occurred in a rejected name.
- Do not merge historical development trades into prospective statistics.
- Do not open the previously sealed March development holdout to rescue this setup.
- Do not add indicator votes/periods to this exact version after seeing its results; an indicator-enhanced successor requires a new version and new untouched evidence.
