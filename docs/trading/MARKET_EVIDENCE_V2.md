# Market Evidence V2

`market-evidence-v2` is the prospective data and execution-authority contract for Omnix V2 gap-pullback trading. Its purpose is to make missing or inconsistent market inputs explicit and fail closed rather than allowing a partially observed cohort to masquerade as a valid trading session.

## Authority model

The strategy remains deterministic. AI, Stoch overlays, catalyst research, frozen spreads, and diagnostic fallbacks never place or authorize an order.

A strategy-origin BUY can reach the paper repository only after a `trade_authorization` assessment is persisted immediately in front of `place_order`. Protective and force-flat SELL orders retain their independent safety path.

`TradeAuthorizationAssessment.authorized` is structurally required to equal the conjunction of all of these predicates:

- candidate is a valid materialized source member;
- frozen morning evidence is eligible;
- the entire immutable source session is evaluable;
- causal regular-session 1-minute bar coverage is ready;
- deterministic strategy state is `entry_ready`;
- a fresh execution observation exists;
- that observation is execution eligible and passes the live spread limit;
- deterministic risk sizing is allowed;
- the entry window is open;
- the authoritative execution provider is ready;
- provider circuit/readiness is clear;
- the strategy kill switch is clear;
- V2 qualification authorizes AUTO PAPER;
- the strategy profile fingerprint matches the evidence profile;
- the market-evidence policy version matches `market-evidence-v2`.

Any false predicate produces a denied authorization event and no BUY order.

## Immutable source accounting

Finviz Top Gainers remains the managed V2 discovery source. Every symbol observed in the atomic first-page source cohort receives one immutable `SourceMemberDisposition`:

- `materialized`
- `filtered_gap`
- `filtered_price`
- `unsupported_instrument`
- `enrichment_failed`
- `provider_unavailable`

The disposition list must have the same order and cardinality as `source_candidate_symbols`. Materialized disposition instrument IDs must exactly equal the frozen candidate set.

This prevents provider/enrichment failures from silently shrinking the universe into a survivor cohort.

## Premarket liquidity and TOD RVOL

Prospective V2 morning liquidity uses a versioned `PremarketLiquidityEvidence` record.

The managed policy is:

- provider: Alpaca IEX;
- feed: IEX;
- current premarket cumulative volume and historical same-clock baseline use the same feed;
- only fully completed one-minute bars are included;
- current and historical samples stop at the same latest completed premarket minute;
- at least five historical baseline sessions are required;
- numerator, denominator mean, baseline session count, premarket bar count, non-zero-volume bar count, coverage ratio, provider and feed are persisted.

Yahoo extended-hours data may remain diagnostic evidence when Alpaca evidence is unavailable, but it carries a different evidence policy and cannot qualify a V2 AUTO PAPER candidate under `market-evidence-v2`.

## Spread semantics

Frozen morning spread is research/quality evidence only.

It cannot reject or authorize the later BUY by itself. The hard spread gate is evaluated against a fresh entry-time execution observation from the authoritative execution provider immediately before authorization.

This avoids confusing a stale premarket quote with the executable spread at the strategy decision.

## Regular-session bar coverage

`BarCoverageAssessment` proves that causal 1-minute history is usable. It checks:

- the 09:30 ET opening minute is present;
- every expected regular-session minute through the latest fully completed minute is present;
- the latest expected minute is present;
- data latency remains inside the configured freshness allowance.

Canonical AUTO PAPER does not switch evidence providers when its bar history is incomplete. SHADOW diagnostic analysis may use the documented Alpaca-IEX indicator fallback, but that result remains research-only and cannot authorize an order or promotion evidence.

## Session evaluability

The session contract distinguishes data quality from strategy outcome:

- `complete`: all source members are accounted for and all materialized candidates have valid morning evidence;
- `completed_no_trigger`: clean replay completed but the strategy generated no trigger;
- `zero_candidate_scan`: a completely accounted source cohort legitimately filtered to no candidates;
- `partial_data`: some candidates are evaluable but source/member evidence is incomplete or failed;
- `not_evaluable_data`: the session cannot be meaningfully evaluated;
- `provider_unavailable`: an authoritative provider dependency was unavailable.

Only clean `complete` / `completed_no_trigger` replay sessions are eligible to contribute V2 promotion evidence. Partial or unavailable sessions never become zero-trade datapoints.

## V2 qualification reset

The V2 strategy profile fingerprint includes `market-evidence-v2` and the new spread-authority semantics.

The qualification and replay versions are:

- `v2-prospective-qualification-2`
- `v2-shadow-replay-2`

Old replay events or old evidence-policy profiles cannot authorize the new cohort. A replay trade counts only when a matching `v2_shadow_replay_session` establishes that the session was clean and qualification eligible.

This reset is intentional: old evidence was collected under materially different data semantics and must not leak into AUTO PAPER approval.

## AI research behavior

Both AI arms remain research-only with `execution_authority=false`.

Missing execution observations, incomplete bar coverage, and invalid morning evidence are persisted as typed `ai_shadow_input_gap` events. They are not converted into model `skip` decisions.

The every-minute AI arm is a cohort experiment. It runs only when every morning-eligible member of the immutable cohort is present and all rows share the exact same finalized-minute watermark. It waits rather than issuing a smaller survivor-cohort batch.

The event-driven arm keeps immediate hard triggers for execution eligibility, halt state, position state and thesis invalidation. Softer state changes retain the bounded cooldown behavior.

## Regression evidence

Focused tests:

```powershell
python -m pytest src/tests/trading/test_trading_market_evidence_v2.py -q --tb=short
```

Deterministic AUTO PAPER end-to-end:

```powershell
python -m pytest src/tests/trading/test_trading_auto_paper_e2e_replay.py -q -s --tb=short
```

PostgreSQL durable AUTO PAPER end-to-end:

```powershell
$env:OMNIX_TEST_DATABASE_URL="postgresql://omnix:omnix@127.0.0.1:5432/omnix_test"
$env:OMNIX_DATABASE_URL=$env:OMNIX_TEST_DATABASE_URL
python -m pytest src/tests/persistence/test_trading_auto_paper_e2e_integration.py -q -s --tb=short
```

Real-provider AI SHADOW end-to-end:

```powershell
$env:OMNIX_RUN_LIVE_AI_TRADING_E2E="1"
$env:OMNIX_AI_TRADING_E2E_EXPECTED_PROVIDER="chatgpt_codex"
python -m pytest src/tests/trading/test_live_ai_trading_e2e.py -q -s --tb=short
```

The normal `Omnix Trading terminal gates` workflow runs the complete `src/tests/trading` suite on the immutable PR head. The PostgreSQL workflow separately covers durable repository behavior.
