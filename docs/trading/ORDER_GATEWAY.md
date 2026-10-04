# Paper order gateway

Every paper order is placed, cancelled or replaced through `app/trading/order_gateway.py`. A guard test (`src/tests/trading/test_order_gateway.py`) fails if any other module calls the paper repository's order methods.

## Authorities

Each order carries the reason it may exist:

| Authority | Used by | May open or add exposure |
|---|---|---|
| `reduce_only` | protective exits (strategy monitor, paper protection monitor), the raw `POST .../orders` route, replacements | no |
| `manual_risk` | `POST .../risk-orders`, after the server's risk preview sized and allowed the entry | yes |
| `strategy_entry` | strategy entries, after `StrategyEntryAuthorizer` proved the entry for its own trade attempt | yes |

A strategy entry is authorized from its own trade attempt's events: risk decision, universe and profile fingerprint. A later or earlier attempt for the same instrument never authorizes it. The assessment is persisted as a `trade_authorization` strategy event, and a denial raises `trade_authorization_denied:<reason codes>`.

## Checks in the order's transaction

Under the account row lock, in the transaction that writes the order:

1. The account exists and is enabled.
2. An idempotency key already used returns the order placed with it (a different payload is `paper_idempotency_payload_mismatch`).
3. A buy that only covers an open short, and a sell covered by the unreserved long position, reduce exposure and need nothing more.
4. Any other order opens or adds exposure. It needs `manual_risk` or `strategy_entry` authority (`paper_order_requires_entry_authority`), and no kill switch may be engaged for the workspace, the account or the order's strategy (`trading_kill_switch_engaged:<scope>`).
5. Accounts are long-only: a sell with no long position is `paper_short_not_allowed` unless the account's `allow_short` is set, and the short is then an entry under step 4. A sell larger than the unreserved position is `insufficient_paper_position`.
6. Cash for a buy is reserved (`insufficient_paper_cash`).

A replacement cancels the old order and places the new one in one transaction. If the replacement is rejected, the old order stays open with its reservation.

## Kill switches

`omnix_trading_kill_switches` holds one row per switch: scope `global` (scope id empty), `account` or `strategy`. A missing row means released. `TradingKillSwitchRepository.set(scope, scope_id, engaged=..., reason=...)` engages or releases a switch and counts revisions. An engaged switch stops entries and never stops exits. The strategy configuration's own `risk.kill_switch` still denies that strategy's entries during authorization.
