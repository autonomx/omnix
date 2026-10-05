# Adding a trading strategy

A strategy is one module plus one entry in `app/trading/strategies/registrations.py`. The test `src/tests/trading/test_strategy_registry.py::test_a_strategy_is_added_by_one_module_and_one_registration` follows these steps with `src/tests/trading/fake_breakout_strategy.py`.

## 1. Write the module

Implement the protocol in `app/trading/strategies/contract.py`:

```python
class MyBreakoutStrategy:
    kind = "my_breakout_v1"              # persisted as strategy_kind; never reuse a kind
    version = "1.0.0"
    config_model = MyBreakoutConfig      # a pydantic model with a strategy_version field
    data_requirements = DataRequirements(interval="1m", lookback_bars=60)
    allowed_modes = ("off", "shadow")

    def evaluate(self, ctx: StrategyContext) -> list[Proposal]:
        ...
```

- `evaluate` must be pure and deterministic. It reads only `ctx` (configuration, risk profile, evaluation time and the closed bars for each instrument) and returns proposals. It never calls providers, writes state or places orders.
- The runner passes only bars that had closed by `ctx.observed_at`.
- Instruments come from the configuration's active universe, or from `data_requirements.instruments` when the configuration has none.

## 2. Register it

Add one entry to `STRATEGY_REGISTRY` in `registrations.py`:

```python
STRATEGY_REGISTRY = StrategyRegistry((
    ...,
    MyBreakoutStrategy(),
))
```

From then on:

- persisted configurations accept the kind, and `config` is parsed by `config_model`;
- the API schema lists the kind and the config model;
- the `trading.strategy_runner` scheduled task evaluates every enabled, non-archived configuration of the kind each minute, and records each proposal as a `proposal` strategy event (once per strategy, instrument, reason and minute).

## Limits

- Runner strategies are shadow-only. The registry refuses `auto_paper` until runner proposals go through the order gateway's attempt-bound authorization (`docs/trading/ORDER_GATEWAY.md`).
- `gap_pullback_v1` and `stoch_rsi_5m_v1` are registered as monitor-owned. The strategy monitor still runs them, and the registry only validates their configurations and modes.
