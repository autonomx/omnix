# Yahoo Evidence & Recovery Hardening — Acceptance Subject

This manifest defines the review subject for Yahoo/data-recovery hardening on
`agent/leader-momentum-diagnostics-v1-1`. The surrounding PR contains other
trading and repository work; those files are not evidence that this roadmap is
complete.

## Core implementation

- `src/app/trading/yahoo_evidence.py`
- `src/app/trading/yahoo_acquisition_monitor.py`
- `src/app/trading/providers/equity.py`
- `src/app/trading/providers/http_runtime.py`
- `src/app/trading/providers/alpaca_iex_status.py`
- `src/app/trading/providers/registry.py`
- `src/app/trading/market_data_recovery.py`
- `src/app/trading/feature_qualification.py`
- `src/app/trading/service.py`
- `src/app/trading/market_evidence.py`
- `src/app/trading/premarket_liquidity.py`
- `src/app/trading/finviz_gapper_discovery.py`

## Strategy-consumer migration

- `src/app/trading/strategy_monitor.py`
- `src/app/trading/strategy_runtime_reliability_fixes.py`
- `src/app/trading/strategy_ai_shadow_v3_monitor.py`
- `src/app/trading/strategy_prospective_economic_monitor.py`

Legacy/v2/deep shadow monitors remain source-compatible but receive the shared
market service through `_CurrentShadowSessionProxy`.

## Runtime registration/diagnostics

- `src/app/gateway/trading_routes.py`
- `src/app/trading/market_data_api.py`
- `src/app/trading/strategy_operations_api.py`

## Acceptance tests

- `src/tests/trading/test_yahoo_evidence_hardening.py`
- `src/tests/trading/test_yahoo_acquisition_monitor.py`
- `src/tests/trading/test_provider_http_runtime_hardening.py`
- `src/tests/trading/test_market_data_recovery.py`
- `src/tests/trading/test_strategy_shadow_general_recovery_contract.py`
- `src/tests/trading/test_strategy_stoch_rsi_gap_recovery.py`
- `src/tests/trading/test_strategy_stoch_rsi_5m_monitor.py`

## Frozen policy during soak

Data hardening must not modify entry thresholds, stop/target geometry,
reward/risk policy, Stoch thresholds, or model decision policy. Any such change
belongs to a separate prospective strategy experiment.

## Phase 11 soak evidence

Session-scoped Yahoo repair/block metrics are durable under
`resources/trading/yahoo_evidence/sessions/YYYY-MM-DD.json` and retrievable
through `GET /api/trading/market-data/yahoo-evidence/diagnostics/{session_date}`.
The report distinguishes repaired evaluations, genuinely blocked evaluations,
repairs that still remained blocked, passed evaluations, and block-reason
counts.

## Promotion rule

Passing unit/CI gates establishes implementation correctness only. The Phase 11
instrumentation is complete, but production confidence still requires multiple
future prospective sessions satisfying the soak gates in
`YAHOO_EVIDENCE_RECOVERY_HARDENING.md`. Future elapsed sessions are not marked
complete synthetically.
