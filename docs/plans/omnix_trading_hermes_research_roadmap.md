# Omnix Trading + Hermes Research — Implementation Roadmap

**Status:** Proposed implementation and qualification contract  
**Target branch:** `agent/trading-auto-strategy-roadmap`  
**Parent program:** PR #1494 automated gap-pullback roadmap  
**Primary strategy:** `gap_pullback_v1`  
**Current strict baseline:** strategy version `1.1.0`  
**Product posture:** Hermes may investigate and propose research actions; Omnix owns evidence, fact derivation, strategy state, risk, and paper execution  
**Execution posture:** no LLM/agent order authority; research remains shadow/non-authoritative until explicitly validated and versioned

---

## 1. Program objective

Build a causal, auditable trading-research layer that uses Hermes to determine **what is still unknown**, while Omnix determines **what was known, what is true as of a specific decision time, and what deterministic research features a strategy is allowed to consume**.

The program must improve catalyst, financing, dilution/supply, novelty, and source-quality research without weakening the existing PR #1494 safety boundary:

- Hermes does not place, size, cancel, or modify orders.
- Hermes does not directly mutate strategy state.
- Hermes does not directly set hard trading flags.
- LLM classifications remain shadow-only until separately validated.
- AUTO PAPER remains authorized by deterministic strategy and server-side risk code only.
- Existing `gap_pullback_v1` `1.0.0` and `1.1.0` replay semantics remain reproducible.
- Nothing learned later may rewrite what Omnix knew earlier.

The core architectural rule is:

> **Hermes determines what still needs investigation. Omnix retrieves and timestamps evidence. Omnix derives versioned facts. AI interpretation remains shadow. A deterministic feature projection is the only research input a strategy may consume. Nothing learned later can rewrite an earlier decision state.**

---

## 2. Non-negotiable invariants

### 2.1 Knowledge-time causality

Every durable research datum must distinguish:

```text
source_published_at
source_available_at
captured_at
omnix_known_at
decision_at
```

Definitions:

- `source_published_at`: timestamp stated by the source when available.
- `source_available_at`: best provider/source timestamp for when the source became publicly available, e.g. SEC acceptance time.
- `captured_at`: when Omnix retrieved the source payload/content.
- `omnix_known_at`: server-assigned timestamp when the evidence/fact became durably available to Omnix. Initially this is equal to durable capture/persist time unless a stronger transactional definition is introduced.
- `decision_at`: strategy evaluation timestamp.

Causal visibility rule:

```text
research item is usable for a strategy decision
IFF
omnix_known_at <= decision_at
```

`source_published_at` or `source_available_at` never grants retroactive strategy visibility.

Example:

```text
SEC filing public at        09:31
Omnix discovers/persists it 09:42
strategy decision           09:36
```

The filing is **not visible** to the 09:36 decision even though it was publicly available.

### 2.2 No hindsight research reconstruction

Historical market-universe reconstruction may remain explicitly approximate as implemented in PR #1494.

Historical **research knowledge** must not be reconstructed from present-day web/SEC state and then treated as if Omnix knew it historically.

Rules:

- captured historical research evidence may be replayed `as_of decision_at`;
- evidence captured after `decision_at` is invisible;
- if no historical captured research exists, research features are `unknown` / `unavailable` for exact replay;
- any future exploratory research reconstruction must be separately labelled and must never qualify as exact causal strategy evidence.

### 2.3 Stable strategy semantics

Do not change `gap_pullback_v1` `1.1.0` semantics in place.

The current legacy behavior, including legacy dilution flags and catalyst scoring, must remain replayable.

Research semantics must be independently versioned:

```text
strategy_version
research_policy_version
fact_schema_version
extractor_version
feature_projection_version
```

Recommended progression:

```text
strategy_version = 1.1.0
research_policy_version = legacy-1

strategy_version = 1.1.0
research_policy_version = trading-research-1-shadow

# only after outcome validation
strategy_version = 1.2.0
research_policy_version = trading-research-1
```

### 2.4 Strategy consumes features, never prose

Persist three layers:

```text
TradingResearchReport
        ↓
TradingFactSet
        ↓
StrategyResearchFeatures
```

The strategy may consume only `StrategyResearchFeatures`.

The strategy must not parse or inspect:

- Hermes prose;
- source snippets;
- raw SEC filings;
- company releases;
- LLM rationales;
- the complete `TradingResearchReport`.

### 2.5 Research facts are initially non-authoritative

Typed facts solve observability and false-positive problems, but they do not automatically become hard trading vetoes.

The initial implementation must:

1. collect typed facts;
2. derive deterministic metrics/features;
3. store them with outcome data;
4. measure predictive value;
5. only then introduce a new versioned research policy / strategy version that makes validated features authoritative.

---

## 3. Target architecture

```text
09:20 MORNING SCAN
        │
        ↓
DETERMINISTIC PRE-FILTER
 gap / price / RVOL / dollar volume / spread / float
        │
        ↓
TRADING RESEARCH COORDINATOR
        │
        ├── Issuer identity / CIK resolver
        ├── SEC EDGAR adapter
        ├── Company IR adapter
        └── Generic web-search adapter
        │
        ↓
IMMUTABLE EVIDENCE STORE
 source timestamps + capture + omnix_known_at
        │
        ↓
HERMES ITERATIVE NEXT-ACTION PLANNER
        ↑
        └── one bounded result/action cycle
        │
        ↓
VERSIONED TRADING RESEARCH REPORT
 human/audit representation
        │
        ↓
VERSIONED TRADING FACT SET
 catalyst + financing + supply + unresolved facts
        │
        ├──────────────────────────┐
        ↓                          ↓
STRATEGY RESEARCH FEATURES       AI SHADOW
small deterministic projection   novelty/classification/relevance
        │
        ↓
FAILED-SELLOFF STRATEGY
5m structure / 1m execution
        │
        ↓
SERVER RISK
        │
        ↓
AUTO PAPER
```

The research loop may continue after the 09:35 entry window opens. New evidence affects only future evaluations because all reads are `as_of decision_at`.

---

## 4. Stable semantic research operation vocabulary

Hermes must reason over semantic operations, not provider implementation details.

Initial trading operation vocabulary:

```text
sec_find_filings
sec_extract_filing
company_find_releases
company_extract_release
web_search
web_extract
evaluate
stop
```

Future operations may be added behind a new contract version, for example:

```text
fda_find_event
clinical_trials_find
court_find_case
```

Hermes never executes these tools directly. It proposes one bounded next action; Omnix validates the request, executes it, persists evidence, and returns a compact evidence summary to Hermes for the next decision.

---

## 5. Proposed backend module layout

Existing modules to preserve and extend:

```text
src/app/trading/
  catalyst_evidence.py
  catalyst_repository.py
  catalyst_shadow.py
  gapper_dataset.py
  strategy_monitor.py
  strategy_range_backtest.py
  strategies/gap_pullback.py

src/app/research/
  planner.py
  executor.py
  quick_search.py

src/app/assist_core/
  hermes_client.py
```

Proposed trading-research modules:

```text
src/app/trading/research/
  __init__.py
  contracts.py
  knowledge_time.py
  issuer_identity.py
  source_authority.py
  coordinator.py
  repository.py
  fact_repository.py
  feature_projection.py
  hermes_contract.py
  hermes_loop.py
  outcome_dataset.py
  adapters/
    base.py
    sec_edgar.py
    company_ir.py
    generic_web.py
  facts/
    catalyst.py
    supply.py
    extraction.py
    metrics.py
```

Do not force generic `src/app/research/` to become trading-specific. Reuse generic web retrieval/extraction infrastructure behind a specialized trading facade.

---

## 6. Core data contracts

### 6.1 Issuer identity

```text
IssuerIdentity
  identity_id
  instrument_id
  symbol
  exchange
  legal_name
  cik
  source
  source_available_at
  captured_at
  omnix_known_at
  confidence
  immutable_fingerprint
```

CIK resolution must be versioned and provenance-carrying because symbol/company mappings change over time.

### 6.2 Research evidence

Extend the current catalyst evidence concept without breaking existing rows/replay.

New evidence contract should support:

```text
TradingEvidence
  evidence_id
  instrument_id
  issuer_identity_id
  evidence_type
  source_type
  source_locator
  source_authority_tier
  source_published_at
  source_available_at
  captured_at
  omnix_known_at
  title/headline
  content_hash
  immutable_fingerprint
  extraction_status
  metadata/facts
```

`omnix_known_at` is server-assigned and immutable.

### 6.3 Supply facts

Replace keyword-only reasoning with typed facts while retaining legacy flags as derived compatibility data.

```text
SupplyFact
  fact_id
  schema_version
  extractor_version
  instrument_id
  supply_type
  status
  shares
  remaining_capacity_usd
  strike_price
  exercise_status
  registration_status
  effective_at
  expires_at
  source_evidence_ids
  resolution_status
  confidence
  generated_at
  omnix_known_at
  immutable_fingerprint
```

Examples of `supply_type`:

```text
atm
warrant
registered_offering
resale_registration
convertible
shelf_registration
equity_line
```

Examples of status semantics:

```text
active
terminated
exhausted
expired
redeemed
exercisable
locked
withdrawn
unknown
```

### 6.4 Catalyst facts

```text
CatalystFactSet
  schema_version
  extractor_version
  primary_confirmed
  same_day
  source_count_primary
  source_count_secondary
  catalyst_type
  source_published_at
  age_minutes_at_projection
  official_filing_present
  company_release_present
  unresolved
  source_evidence_ids
  generated_at
  omnix_known_at
```

AI novelty remains a separate shadow annotation initially.

### 6.5 Derived supply metrics

Derive deterministic metrics from facts, not prose:

```text
potential_dilution_pct_float
remaining_atm_pct_market_cap
in_the_money_warrant_pct_float
registered_resale_pct_float
immediate_supply_risk
supply_resolution_status
```

Initial metrics are observational/shadow unless explicitly enabled by a later research-policy version.

### 6.6 TradingResearchRequest

```text
TradingResearchRequest
  request_id
  contract_version
  strategy_id
  instrument_id
  issuer_identity_id
  requested_at
  decision_context_at
  evidence_cutoff_at
  known_headlines
  known_filings
  objectives
  allowed_operations
  deadline_at
  max_steps
  max_queries
  max_sources
  max_extracts
```

Typical objectives:

```text
catalyst_identity
catalyst_novelty
financing
atm
warrant_overhang
resale_registration
convertibles
source_conflicts
```

### 6.7 Versioned TradingResearchReport

Reports are append-only/versioned, not mutated in place.

```text
TradingResearchReport
  report_id
  report_version
  contract_version
  strategy_id
  instrument_id
  research_started_at
  research_completed_at
  evidence_cutoff_at
  omnix_known_at
  catalyst_status
  supply_status
  research_status
  coverage
  unresolved_facts
  source_evidence_ids
  hermes_trace_id
  planner_backend
  stop_reason
  immutable_fingerprint
```

Statuses:

```text
catalyst_status = confirmed | probable | unresolved | absent
supply_status   = clear | risk_found | unresolved
research_status = complete | partial | timed_out | failed
```

Example report sequence:

```text
09:27 report-v1  catalyst confirmed, supply unknown
09:32 report-v2  SEC checked, warrants detected/status unresolved
09:38 report-v3  warrants registered + exercisable
```

At `decision_at=09:36`, only report-v1/v2 may be selected.

### 6.8 TradingFactSet

```text
TradingFactSet
  fact_set_id
  schema_version
  extractor_version
  strategy_id
  instrument_id
  report_id
  generated_at
  omnix_known_at
  catalyst
  supply
  completeness
  unresolved_facts
  evidence_ids
  immutable_fingerprint
```

### 6.9 StrategyResearchFeatures

Small deterministic projection only:

```text
StrategyResearchFeatures
  projection_version
  instrument_id
  fact_set_id
  decision_at
  primary_catalyst_confirmed
  catalyst_same_day
  catalyst_fresh
  catalyst_age_minutes
  immediate_supply_risk
  supply_resolution_status
  research_status
  unresolved_supply
  source_authority_sufficient
  immutable_fingerprint
```

For `1.1.0`, these features are recorded only and do not alter existing strategy decisions.

---

## 7. Persistence and query rules

### 7.1 Append-only / immutable research records

Evidence, reports, fact sets, feature projections, and Hermes actions/results are append-only. Corrections create a new version linked to superseded data; historical rows are not rewritten.

### 7.2 `as_of` repository reads

Add explicit causal read APIs. Conceptually:

```python
list_evidence_as_of(
    instrument_id,
    known_at_lte=decision_at,
)

latest_report_as_of(
    instrument_id,
    known_at_lte=decision_at,
)

latest_fact_set_as_of(
    instrument_id,
    known_at_lte=decision_at,
)

research_features_as_of(
    instrument_id,
    decision_at,
    projection_version,
)
```

The strategy/historical-replay path must not use unrestricted `list_evidence()`.

### 7.3 Database migration posture

Add new trading migrations rather than changing historical migration semantics.

Expected tables, names subject to existing repository naming conventions:

```text
omnix_trading_issuer_identities
omnix_trading_research_evidence
omnix_trading_research_actions
omnix_trading_research_reports
omnix_trading_supply_facts
omnix_trading_fact_sets
omnix_trading_research_features
omnix_trading_research_outcomes
```

Indexes must support:

```text
(workspace_id, instrument_id, omnix_known_at)
(workspace_id, strategy_id, instrument_id, omnix_known_at)
(workspace_id, immutable_fingerprint)
```

Uniqueness/fingerprint rules must preserve tenant isolation.

---

## 8. Source authority model

Source authority is independent of extraction quality.

Initial tiers:

```text
Tier 1 — primary/authoritative
  SEC EDGAR
  FDA / government source
  Company IR
  ClinicalTrials.gov
  court/government records

Tier 2 — high-quality secondary
  Reuters
  Bloomberg
  Dow Jones
  recognized financial news

Tier 3 — aggregation / specialist secondary
  Yahoo aggregation
  industry publications

Tier 4 — low-authority discovery
  blogs
  social media
  forums
```

A fully extracted Tier 4 page must not outrank a Tier 1 primary source merely because extraction succeeded.

Coverage should be explicit, not a percentage:

```text
SEC checked                  yes/no/failed
Company IR checked           yes/no/failed
Recent news checked          yes/no/failed
Prior 30-day novelty checked yes/no/failed
ATM status resolved          yes/no
Warrant status resolved      yes/no
Resale registration resolved yes/no
Convertible exposure resolved yes/no
```

---

# 9. Delivery phases

## HTR-0 — Architecture contract and regression baseline

### Goal

Freeze the safety, causality, and versioning contract before adding retrieval code.

### Deliverables

- Architecture/ADR documenting:
  - no Hermes execution authority;
  - knowledge-time rule;
  - no hindsight research reconstruction;
  - strategy/research-policy independent versioning;
  - report → fact set → feature projection layering.
- Golden regression fixtures proving `gap_pullback_v1` `1.1.0` decisions remain unchanged.
- Legacy catalyst/dilution behavior tagged as `legacy-1` research semantics.

### Acceptance

- Existing `1.1.0` strategy fixtures produce byte/field-equivalent decisions before/after HTR-0.
- No research module imports paper order-placement APIs.
- CI contains an architecture test that prevents Hermes/research modules from calling order execution APIs.

### Gate

Do not start HTR-1 until reproducibility and import-boundary tests are green.

---

## HTR-1 — Issuer identity and CIK resolution

### Goal

Create point-in-time issuer identity required by authoritative source adapters.

### Deliverables

- `IssuerIdentity` contract.
- CIK/company resolution service for US equities.
- Durable repository with provenance and `omnix_known_at`.
- Symbol/company-change-aware resolution rules.
- UI/debug endpoint for inspecting issuer identity provenance.

### Tests

- symbol → CIK happy path;
- symbol reused/company renamed;
- missing/ambiguous identity;
- future-dated identity invisible to earlier `as_of` read;
- tenant isolation.

### Gate

No SEC research is accepted without a resolved issuer identity or explicit unresolved status.

---

## HTR-2 — SEC EDGAR authoritative adapter

### Goal

Make SEC the first authoritative financing/supply source.

### Deliverables

- semantic adapter operations:
  - `sec_find_filings`;
  - `sec_extract_filing`.
- form support initially focused on:
  - 8-K;
  - 10-Q / 10-K;
  - S-1 / S-1/A;
  - S-3 / S-3/A;
  - 424B3 / 424B5;
  - prospectus supplements;
  - registration-effectiveness/withdrawal information where obtainable.
- source acceptance/publication timestamps.
- SEC-specific cache/rate-limit/User-Agent behavior.
- immutable source capture and content hashes.

### Tests

- acceptance timestamp preserved;
- amendment ordering;
- filing extraction failure does not fabricate facts;
- rate-limit/backoff behavior;
- duplicate filing capture is idempotent;
- evidence `omnix_known_at` is server-assigned.

### Gate

SEC adapter must be usable independently of Hermes.

---

## HTR-3 — Company IR + generic source adapter contracts

### Goal

Establish the final semantic action vocabulary before iterative Hermes is introduced.

### Deliverables

- adapter protocol common to trading research.
- Company IR operations:
  - `company_find_releases`;
  - `company_extract_release`.
- Generic web facade backed by existing Omnix Quick Search:
  - `web_search`;
  - `web_extract`.
- provider-neutral source records.
- explicit source-authority classification.

### Tests

- primary vs secondary source authority preserved;
- generic search provider can change without Hermes contract change;
- source adapter failure is explicit and non-authoritative;
- extraction status does not alter authority tier.

### Gate

Hermes operation names are frozen at contract version `trading-research-1` before HTR-8.

---

## HTR-4 — Typed catalyst and supply schemas

### Goal

Introduce structured facts without changing `1.1.0` trading decisions.

### Deliverables

- `SupplyFact` schema.
- `CatalystFactSet` schema.
- schema/extractor/policy version fields.
- legacy `dilution_flags` retained as compatibility output.
- deterministic metric contracts.

### Tests

Serialization/fingerprint/golden-schema tests for every fact type and status.

### Gate

No typed fact is execution-authoritative in this phase.

---

## HTR-5 — Deterministic supply parser + adversarial corpus

### Goal

Replace naive keyword meaning with status-aware structured extraction.

### Required adversarial fixtures

The parser must distinguish at minimum:

```text
"at-the-market offering is active"
"previous at-the-market offering was terminated"
"ATM facility was exhausted"
"all outstanding warrants were exercised"
"warrants are exercisable at $1.50"
"warrants expire above current price"
"registration statement was withdrawn"
"resale registration became effective"
"convertible notes were repaid"
"convertible notes remain outstanding"
```

### Deliverables

- deterministic extraction pipeline;
- status-resolution/confidence field;
- source evidence links;
- derived metrics:
  - potential dilution % float;
  - remaining ATM % market cap;
  - ITM warrant % float;
  - registered resale % float;
  - immediate supply risk.

### Acceptance

- adversarial false-positive corpus passes;
- unresolved text yields `unknown/unresolved`, never fabricated `clear`;
- legacy flags can still be reproduced for `legacy-1`.

### Gate

Do not wire typed facts into hard strategy vetoes.

---

## HTR-6 — Knowledge-time persistence and `as_of` reads

### Goal

Make "what Omnix knew" enforceable in repository APIs.

### Deliverables

- `omnix_known_at` columns/fields for new research records.
- causal repository APIs:
  - `list_evidence_as_of`;
  - `latest_report_as_of`;
  - `latest_fact_set_as_of`;
  - `research_features_as_of`.
- transaction/server ownership of knowledge timestamps.
- static/architecture tests preventing strategy/replay from using unrestricted research reads.

### Critical regression test

```text
filing source_available_at = 09:31
captured/omnix_known_at    = 09:42
decision_at                = 09:36
```

Expected: filing invisible.

At `decision_at=09:43`: visible.

### Gate

No strategy-facing research integration before this phase passes.

---

## HTR-7 — Research request/report/fact-set contracts

### Goal

Create immutable trading-specific orchestration contracts.

### Deliverables

- `TradingResearchRequest`.
- append-only/versioned `TradingResearchReport`.
- `TradingFactSet`.
- `StrategyResearchFeatures` shadow projection.
- completeness/unresolved-fact fields.
- report selection by `as_of decision_at`.

### Acceptance

Given report-v1/v2/v3 at 09:27/09:32/09:38:

- 09:30 decision → v1;
- 09:36 decision → v2;
- 09:40 decision → v3.

No report is mutated in place.

---

## HTR-8 — Iterative one-action Hermes planning

### Goal

Turn Hermes from a one-shot research planner into a bounded next-action planner for trading research.

### Loop

```text
current evidence summary
        ↓
Hermes proposes exactly one semantic next action
        ↓
Omnix validates action against allowlist/budget/deadline
        ↓
Omnix executes adapter action
        ↓
Omnix persists immutable evidence
        ↓
compact evidence/unresolved-fact summary returned to Hermes
        ↓
repeat until stop/budget/deadline
```

### Rules

- one action per Hermes decision;
- no arbitrary tool names;
- no shell/files/GitHub/order tools;
- hard max steps/queries/sources/extracts;
- hard wall-clock deadline;
- every action/result persisted with trace ID;
- local fallback may stop safely but must not impersonate Hermes findings;
- Hermes output remains proposal-only JSON.

### Tests

- search result causes a different second action;
- financing clue triggers SEC follow-up;
- ambiguous warrants trigger targeted extraction;
- budget exhaustion;
- deadline timeout;
- malformed Hermes response;
- Hermes unavailable;
- unknown operation blocked;
- attempted order/tool mutation blocked.

### Gate

Iterative Hermes may only create research evidence/reports; it may not alter `active_universe_id`, order state, risk state, or strategy configuration.

---

## HTR-9 — Source authority, completeness, unresolved facts

### Goal

Make research quality inspectable without misleading percentage scores.

### Deliverables

Explicit status model:

```text
catalyst_status
supply_status
research_status
```

Explicit coverage matrix:

```text
SEC
Company IR
recent news
prior-news novelty
ATM
warrants
resale registration
convertibles
```

### Acceptance

UI/API can distinguish:

- complete + clean;
- complete + risk found;
- partial due unresolved warrants;
- timed out;
- failed source adapter;
- no primary-source confirmation.

---

## HTR-10 — Shadow novelty/relevance AI

### Goal

Use LLM reasoning where semantic comparison adds value without granting execution authority.

### Deliverables

Shadow annotations for:

```text
novelty = new | incremental | recycled | uncertain
relevance
catalyst class
conflict summary
confidence
```

The classifier must cite only supplied evidence IDs and remain `shadow_only=true`.

### Tests

- similar prior announcement marked as possible recycled/incremental;
- missing evidence produces uncertainty, not confidence;
- classifier cannot emit an order/size/action authority field;
- future evidence excluded by `as_of` selection.

### Gate

No novelty output affects AUTO PAPER in HTR-10.

---

## HTR-11 — Trading research UI and operator audit trail

### Goal

Expose what was checked, what is known, and what remains unresolved.

### UI target

For each candidate:

```text
Catalyst
  ✓ Same-day catalyst identified
  ✓ Company source confirmed
  ✓ Secondary confirmation

Novelty
  ✓ Prior 30-day news checked
  ⚠ Similar announcement found

Supply
  ✓ S-1 / S-3 checked
  ✓ 424B3 / 424B5 checked
  ⚠ Warrants detected
  ? Remaining exercisable shares unresolved

Research status
  PARTIAL — supply ambiguity

Hermes next/last action
  Inspect warrant registration statement
```

### Required views

- report-version timeline;
- evidence/source list with authority tier;
- fact-set view;
- derived metrics;
- Hermes action trace;
- exact `omnix_known_at` timestamps;
- "visible to decision at" indicator.

### UX rule

Do not display synthetic "92% complete" scores.

---

## HTR-12 — Automatic morning research funnel

### Goal

Use the 09:20 → 09:35 window efficiently and continue causally afterward.

### Default funnel

```text
~50 morning discoveries
        ↓ cheap deterministic filters
~10–15 plausible names
        ↓ automatic SEC + headline/IR harvest
~5–8 plausible names
        ↓ Hermes only where ambiguity remains
~3–5 researched candidates
        ↓ deterministic structure monitoring
0–3 setups
```

### Scheduling rules

- research collection may run while strategy mode is `off`, because archival is evidence collection, not trading authority;
- expensive Hermes research is prioritized by uncertainty/expected value of information;
- obvious clean primary-source cases should require little/no Hermes work;
- ambiguous financing/recycled-news cases get deeper research;
- later research updates future decisions only.

### Logging

Extend `resources/logs/trade/auto_trading.jsonl` or add a dedicated research stream with:

- research run/trace ID;
- candidate;
- action;
- adapter;
- evidence IDs;
- report/fact versions;
- `omnix_known_at`;
- budget/deadline state;
- unresolved facts;
- redacted provider secrets.

---

## HTR-13 — Outcome dataset and research-feature attribution

### Goal

Measure whether research adds edge before changing strategy gates.

### Dataset per candidate/setup

```text
session_date
instrument_id
strategy_version
research_policy_version
feature_projection_version
market-universe origin/fidelity
research status
source authority coverage
catalyst features
supply metrics
novelty shadow label
strategy rejection/trigger state
entry/exit if any
MFE
MAE
R result
2R-before--1R label
time-to-MFE
time-to-stop
data-quality flags
```

### Required analyses

Compare at minimum:

- structure-only baseline;
- primary catalyst confirmed vs not;
- same-day primary catalyst vs secondary only;
- clean resolved supply vs unresolved;
- immediate supply risk buckets;
- novelty shadow classes;
- research complete vs partial;
- captured-exact vs reconstructed market universes.

### Anti-leakage rule

Outcome labels may never feed fact extraction or feature projection for the same historical decision.

---

## HTR-14 — Statistical validation and promotion criteria

### Goal

Define evidence required before research features may alter trading authorization.

### Minimum promotion questions

- Does the feature improve expectancy/R distribution out of sample?
- Does it improve 2R-before--1R probability?
- Is the effect stable across symbols/time periods?
- Is it robust after transaction-cost assumptions?
- Is sample size sufficient?
- Does it survive exact/captured-only subsets?
- Is the feature observable reliably before decisions?
- Is unresolved/missing data handled safely?

### Promotion output

Produce an explicit validation report identifying:

```text
feature
sample size
in-sample effect
out-of-sample effect
confidence interval / uncertainty
recommended action:
  observe_only
  score_only
  soft_gate
  hard_gate
```

### Gate

No research feature becomes authoritative merely because an LLM/Hermes rationale sounds convincing.

---

## HTR-15 — New versioned research-authoritative strategy policy

### Goal

Only after HTR-13/14 show predictive value, introduce a new deterministic execution policy.

### Options

Preferred:

```text
strategy_version = 1.2.0
research_policy_version = trading-research-1
```

Alternative if price/structure semantics remain identical:

```text
strategy_version = 1.1.0
research_policy_version = trading-research-1-authoritative
```

The choice must be recorded in an ADR. If any previously identical `1.1.0` input can produce a different authorization outcome, prefer `1.2.0`.

### Requirements

- `1.0.0` and `1.1.0/legacy-1` historical replay unchanged;
- new policy explicitly chooses which validated research features are:
  - informational;
  - scoring;
  - soft gates;
  - hard gates;
- every decision log records strategy/research/fact/projection versions;
- backtest/paper runner consumes exact same projection and policy code.

---

# 10. Backtesting rules

## 10.1 Exact research replay

Exact historical research replay requires evidence/facts/reports captured at the time.

For decision `D`:

```text
eligible research = records where omnix_known_at <= D
```

The latest eligible report/fact set may be used.

## 10.2 Missing historical research

If exact captured research is absent:

```text
research_status = unavailable
research_features = unknown/default non-authoritative values
```

Do not search today's SEC/web and inject those facts into the historical decision.

## 10.3 Reconstructed market universe interaction

A reconstructed market universe may still be backtested under the existing explicitly approximate market-data fidelity rules, but research fidelity must be separately reported:

```text
market_fidelity   = reconstructed_current_listings_iex
research_fidelity = unavailable
```

Do not blur the two into a single quality label.

## 10.4 Report version replay fixture

Required test fixture:

```text
report-v1 known 09:27
report-v2 known 09:32
report-v3 known 09:38
```

Expected decisions:

```text
09:30 → v1
09:36 → v2
09:40 → v3
```

---

# 11. API surface

Exact route names should follow current Trading API conventions, but target capabilities are:

```text
GET  issuer identity for instrument
GET  research status/report timeline for instrument
GET  evidence as-of timestamp
GET  fact set as-of timestamp
GET  research features as-of timestamp
POST start/continue bounded research for candidate
GET  research action trace
GET  outcome/research attribution summary
```

Research writes must not expose generic caller-controlled `omnix_known_at`.

No research route may expose order placement/cancel/sizing authority.

Generated OpenAPI/types must remain authoritative and pass the existing Trading contract drift check.

---

# 12. Logging and observability

Extend the trade audit system so a decision can be reconstructed from logs plus durable records.

Each research log entry should include where relevant:

```text
trace_id
strategy_id
instrument_id
operation
adapter
source IDs
evidence IDs
report ID/version
fact_set_id
projection version
requested_at
captured_at
omnix_known_at
decision_at
budget remaining
deadline
research status
unresolved facts
error code
```

Never log:

- SEC/API secrets;
- Hermes/provider keys;
- authorization headers;
- raw credentials.

Research logging failure remains non-authoritative and must not change strategy execution.

---

# 13. CI and qualification gates

Each implementation phase must keep existing PR #1494 Trading gates green.

Add dedicated tests for:

### Architecture

- Hermes/research modules cannot import order-placement functions.
- strategy cannot import Hermes client or parse research prose.
- `1.1.0/legacy-1` strategy regression fixtures are stable.

### Persistence

- tenant isolation;
- immutable fingerprints;
- append-only report versions;
- `as_of` indexes/queries;
- PostgreSQL migration/health checks.

### Causality

- later capture invisible to earlier decision;
- future report invisible;
- historical replay selects latest eligible report only;
- present-day research cannot enter exact historical replay.

### Source adapters

- SEC rate limits/failures;
- IR extraction failures;
- search provider independence;
- source authority tier.

### Fact extraction

- adversarial financing/supply corpus;
- unresolved status behavior;
- parser version reproducibility.

### Hermes

- one-action contract;
- allowlist enforcement;
- budget/deadline enforcement;
- malformed response;
- timeout/fallback;
- no execution action accepted.

### UI

- light/dark mode;
- global text scaling;
- report timeline;
- explicit coverage states;
- fullscreen Strategies/AI Research views;
- accessibility labels for statuses.

---

# 14. Rollout policy

### Stage A — evidence only

HTR-1 through HTR-9.

No strategy effect.

### Stage B — AI/fact shadow

HTR-10 through HTR-12.

Research visible to operators and logged with outcomes, still no strategy authorization effect.

### Stage C — measurement

HTR-13 through HTR-14.

Collect and analyze enough observations to judge predictive value.

### Stage D — versioned deterministic promotion

HTR-15 only after explicit validation.

Any execution effect requires a new pinned research policy and, if authorization semantics differ, a new strategy version.

---

# 15. Explicit non-goals

This roadmap does **not** authorize:

- Hermes placing/canceling/modifying orders;
- Hermes sizing positions;
- Hermes changing stops/targets;
- Hermes editing strategy configuration autonomously;
- LLM prose being parsed by the strategy;
- present-day research being backfilled as historical knowledge;
- silent modification of `gap_pullback_v1` `1.1.0` semantics;
- immediate hard vetoes based solely on newly typed supply facts;
- production live-broker execution.

---

# 16. Final definition of done

The Hermes trading-research program is complete when all of the following are true:

1. Issuer/CIK identity is durable and point-in-time attributable.
2. SEC and Company IR primary-source retrieval is available behind semantic adapters.
3. General web discovery remains provider-neutral and secondary to authoritative sources.
4. Evidence has immutable knowledge-time semantics.
5. Causal `as_of` repository reads are the only strategy/replay research path.
6. Supply/catalyst facts are typed, versioned, provenance-linked, and adversarially tested.
7. Hermes performs bounded iterative one-action planning and cannot execute tools directly.
8. Reports are immutable/versioned and late evidence cannot rewrite earlier decisions.
9. The strategy consumes only deterministic `StrategyResearchFeatures`, never prose.
10. AI novelty/relevance remains shadow until validated.
11. UI shows explicit source/status coverage and unresolved facts rather than synthetic completeness percentages.
12. Automatic morning research archives point-in-time evidence for future exact replay.
13. Outcome datasets connect research features to MFE/MAE/R without leakage.
14. Statistical validation determines whether any feature deserves promotion.
15. Any promoted research gate is pinned to a new explicit research-policy/strategy version.
16. Existing `1.0.0` and `1.1.0/legacy-1` replays remain unchanged.
17. Trading, PostgreSQL, frontend, TypeScript, Playwright, OpenAPI generation, and generated-contract drift gates are green.

The end-state must preserve this invariant:

> **Hermes determines what is still unknown. Omnix determines what is true and when it became known. AI interprets in shadow. Deterministic versioned policy decides whether a setup qualifies. Nothing learned later is allowed to rewrite an earlier decision state.**
