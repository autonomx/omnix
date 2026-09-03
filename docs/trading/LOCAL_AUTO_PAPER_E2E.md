# Local AUTO PAPER end-to-end replay

This test answers a specific production question: **if a V2 strategy is already
authorized for AUTO PAPER and today's immutable universe is available, will the
runtime actually produce a paper order, fill it, create a position, and activate
strategy protection?**

It is intentionally deterministic and can be run locally by Codex without the
Omnix server, external market APIs, an LLM, or a broker connection. It uses the
real V2 qualification evaluator, strategy monitor, risk sizing, paper-order
models, paper fill rules, and paper monitor.

## Run it

From the repository root:

```powershell
python -m pytest src/tests/trading/test_trading_auto_paper_e2e_replay.py -q -s
```

A successful run prints a line similar to:

```text
AUTO PAPER E2E PASS symbol=TLYS order=strat-... qty=... fill=... position=... protection=active
```

## PostgreSQL-backed check

For the strongest local check, point Omnix at a **dedicated test PostgreSQL
database** and run the persistence-backed E2E:

```powershell
$env:OMNIX_TEST_DATABASE_URL="postgresql://omnix:omnix@127.0.0.1:5432/omnix_test"
$env:OMNIX_DATABASE_URL=$env:OMNIX_TEST_DATABASE_URL
python -m pytest src/tests/persistence/test_trading_auto_paper_e2e_integration.py -q -s
```

`bootstrap_local_tenant()` applies the repository migrations. The test uses
unique strategy/account IDs and then runs the production
`TradingStrategyRepository` + `TradingPaperRepository` path. A pass requires
the paper order, fill, cash movement, position, strategy events, and pending
strategy protection to be persisted in PostgreSQL.

Use only a disposable/test database for this command.

## What it proves

The test exercises the production:

1. Exact managed-Finviz V2 profile identity and profile-bound qualification.
2. Reviewed qualification evidence cannot be inherited by an arbitrary V2 variant.
3. V2 current-session archive lookup used by AUTO PAPER.
4. Finviz atomic-cohort integrity gate.
5. Complete current-session 1-minute data gate.
6. Deterministic V2 L1 -> B1 -> higher-L2 -> VWAP/B1 break evaluator.
7. Entry proposal arbitration.
8. Execution-observation eligibility and spread checks.
9. Server-side risk sizing.
10. Strategy protection arming before order submission.
11. Paper order creation.
12. Paper execution monitor.
13. Shared paper fill/slippage/liquidity rules.
14. Paper position creation.
15. Next-cycle reconciliation from pending protection to active protection.
16. Duplicate-entry prevention on the already-consumed causal bar.

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

The successful AUTO PAPER leg is timestamped as **October 1, 2026**, while
retaining the Sep. 3 cohort and TLYS price example. That is deliberate. The
prospective V2 policy starts August 24 and requires at least 15 distinct sessions
and 20 matched trades, so Sep. 3 itself was too early for a production-reachable
reviewed promotion. Moving only the replay clock allows the test to exercise a
state production can actually reach without lowering or bypassing those floors.

## Authority boundary

The test does **not** monkeypatch AUTO PAPER authorization. It seeds durable,
profile-bound shadow/replay evidence plus the final reviewed economic-policy
event, runs the real V2 qualification evaluator, creates an exact
evidence-fingerprint operator review, and verifies that the evaluator returns
`auto_paper_authorized=true`.

The upstream economic pipeline that earns its final review, plus qualification
thresholds/evidence matching/operator promotion behavior, remain tested
separately in:

```text
src/tests/trading/test_trading_strategy_v2_qualification.py
```

That separation makes this E2E test answer the runtime question cleanly:
**once promotion is valid, does AUTO PAPER actually trade?**

This test remains paper-only. It contains no live-broker adapter and cannot
place a real-money order.
