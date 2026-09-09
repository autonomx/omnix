# Local live AI trading E2E

This test verifies the production AI-shadow trading path with a **real configured LLM provider** while remaining research/paper-only. It cannot create live broker orders.

## What it validates

The test uses the existing September 3 TLYS causal replay fixture and exercises:

1. the configured foreground provider can be resolved;
2. the dedicated trading-research provider is created independently of Chat/Agent;
3. the production AI-shadow monitor resolves the frozen Finviz archive;
4. production 1-minute bars are evaluated into causal feature snapshots;
5. both `minute` and `event` AI policies call the real provider;
6. native structured-output/schema handling returns one valid decision per instrument;
7. both AI batches persist successfully with no LLM error checkpoint;
8. decisions persist with `research_only=true` and `execution_authority=false`;
9. token accounting is populated;
10. the production AI-shadow execution simulator can create a simulated research fill from an actionable decision;
11. no `entry_order_submitted` event or broker/live-order authority is created.

The execution-contract probe is intentionally deterministic. A real model is allowed to decide `SKIP`; that is a valid trading decision and should not make a health test fail. The probe uses a separate synthetic instrument solely to ensure the downstream research-only fill lifecycle is functioning.

## Run on Windows / PowerShell

From the Omnix repository root:

```powershell
$env:OMNIX_RUN_LIVE_AI_TRADING_E2E="1"
python -m pytest src/tests/trading/test_live_ai_trading_e2e.py -q -s --tb=short
```

A successful run prints a line similar to:

```text
LIVE AI TRADING E2E PASS provider=chatgpt_codex model=gpt-5.6-codex live_actions=enter,enter live_batches=2 live_decisions=2 tokens=1234 execution_probe=filled execution_authority=false
```

The exact actions and token count are model-dependent.

## Require a specific provider

For example, to verify that the AI-shadow lane is really using ChatGPT Codex:

```powershell
$env:OMNIX_RUN_LIVE_AI_TRADING_E2E="1"
$env:OMNIX_AI_TRADING_E2E_EXPECTED_PROVIDER="chatgpt_codex"
python -m pytest src/tests/trading/test_live_ai_trading_e2e.py -q -s --tb=short
```

If the configured provider is LM Studio instead, ensure the LM Studio local API is running before executing the test.

For ChatGPT Codex, the Omnix Codex provider must already be configured and the Codex CLI must be installed/authenticated.

## Optional strict model-entry mode

The stable E2E accepts any schema-valid model action because `SKIP` can be a correct answer. If you explicitly want to test whether the current model interprets this replay as an entry setup, enable:

```powershell
$env:OMNIX_RUN_LIVE_AI_TRADING_E2E="1"
$env:OMNIX_AI_TRADING_E2E_REQUIRE_LIVE_ENTRY="1"
python -m pytest src/tests/trading/test_live_ai_trading_e2e.py -q -s --tb=short
```

This mode fails unless at least one of the two live AI policies returns `enter`. Use it as a strategy-behavior probe, not as the normal reliability gate.

## What does not need to be running

The standard live AI E2E does **not** require:

- the Omnix FastAPI server;
- PostgreSQL;
- Finviz/Yahoo/Alpaca network access;
- the AUTO PAPER engine;
- a live broker connection.

Market evidence comes from the frozen September 3 replay fixture so the only external dependency is the LLM provider you intentionally want to test.

## Safety / authority boundary

This test exercises AI-shadow only. The AI result is non-authoritative and the downstream fill is a normalized research simulation. The assertions explicitly require `execution_authority=false` and verify that no production order-submission event is created.
