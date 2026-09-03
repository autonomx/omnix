# Local AUTO PAPER end-to-end replay

This test answers a specific production question: **if a V2 strategy is already
authorized for AUTO PAPER and today's immutable universe is available, will the
runtime actually produce a paper order, fill it, create a position, and activate
strategy protection?**

It is intentionally deterministic and can be run locally by Codex without the
Omnix server, external market APIs, an LLM, or a broker connection.

## Run it

From the repository root:

```powershell
python -m pytest src/tests/trading/test_trading_auto_paper_e2e_replay.py -q -s
```

A successful run prints a line similar to:

```text
AUTO PAPER E2E PASS symbol=TLYS order=strat-... qty=... fill=... position=... protection=active
```

## What it proves

The test exercises the production:

1. V2 current-session archive lookup used by AUTO PAPER.
2. Finviz atomic-cohort integrity gate.
3. Complete current-session 1-minute data gate.
4. Deterministic V2 L1 -> B1 -> higher-L2 -> VWAP/B1 break evaluator.
5. Entry proposal arbitration.
6. Execution-observation eligibility and spread checks.
7. Server-side risk sizing.
8. Strategy protection arming before order submission.
9. Paper order creation.
10. Paper execution monitor.
11. Shared paper fill/slippage/liquidity rules.
12. Paper position creation.
13. Next-cycle reconciliation from pending protection to active protection.
14. Duplicate-entry prevention on the already-consumed causal bar.

The assertion fails if no paper order is submitted or if that order does not
become a paper fill and position.

## Sep. 3 scenario basis

The fixture is
`src/tests/trading/fixtures/2026-09-03-auto-paper-e2e.json`.

It preserves the Sep. 3 frozen Finviz cohort:

`TLYS -> AEHL -> BIAF -> CHPT -> SNOW`.

TLYS is used for the executable scenario because the Sep. 3 journal recorded
approximately $4.92-$4.98 premarket versus a $3.81 prior close, which satisfies
the frozen V2 >=20% gap requirement. CHPT is deliberately not used to force an
entry because its documented premarket gap was only about 18-19%, even though
it later became the session's largest mover.

The fixture also records the journal's provisional TLYS daily O/H/L/close-level
and volume for context.

The 1-minute replay bars are **synthetic causal test bars** scaled to the Sep. 3
TLYS price regime from the already-tested V2 geometry. They are not claimed to
be the actual TLYS minute tape and do not retroactively claim that Omnix should
have traded TLYS on Sep. 3. This distinction is intentional: the Sep. 3 review
did not have authoritative causal 1-minute data.

## Authority boundary

The test injects an **already-authorized** V2 qualification result. It does not
weaken production qualification.

Qualification thresholds, evidence matching, economic review, and operator
promotion review remain tested separately in:

```text
src/tests/trading/test_trading_strategy_v2_qualification.py
```

That separation makes this E2E test answer the runtime question cleanly:
**once promotion is valid, does AUTO PAPER actually trade?**

This test remains paper-only. It contains no live-broker adapter and cannot
place a real-money order.
