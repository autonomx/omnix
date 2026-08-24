import type {
  PaperAccountSnapshot,
  PaperBalance,
  PaperFill,
  PaperLedgerEntry,
  PaperOrder,
  PaperOrderInput,
  PaperPosition,
} from './paperTypes';
import type { MarketBar } from './tradingTypes';

type ReplayResult = {
  snapshot: PaperAccountSnapshot;
  order: PaperOrder;
};

function finite(value: string | number | null | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function decimal(value: number): string {
  if (!Number.isFinite(value)) return '0';
  return value.toFixed(12).replace(/\.?(0+)$/, '') || '0';
}

function timestamp(bar: MarketBar): string {
  return bar.end_time || bar.start_time || new Date().toISOString();
}

function accountBalance(snapshot: PaperAccountSnapshot): PaperBalance | null {
  return snapshot.balances.find((balance) => balance.currency === snapshot.account.base_currency)
    ?? snapshot.balances[0]
    ?? null;
}

function positionFor(snapshot: PaperAccountSnapshot, instrumentId: string): PaperPosition | null {
  return snapshot.positions.find((position) => position.instrument_id === instrumentId) ?? null;
}

function clonePosition(position: PaperPosition): PaperPosition {
  return { ...position };
}

function markToBar(snapshot: PaperAccountSnapshot, bar: MarketBar): PaperAccountSnapshot {
  const close = finite(bar.close);
  return {
    ...snapshot,
    positions: snapshot.positions.map((position) => {
      const quantity = finite(position.quantity);
      const averageCost = finite(position.average_cost);
      return {
        ...position,
        last_price: decimal(close),
        unrealized_pnl: decimal((close - averageCost) * quantity),
      };
    }),
  };
}

/** Create a detached account state. Nothing from this snapshot is persisted. */
export function createReplaySnapshot(source: PaperAccountSnapshot): PaperAccountSnapshot {
  return {
    account: { ...source.account },
    balances: source.balances.map((balance) => ({
      ...balance,
      available: decimal(finite(balance.available) + finite(balance.reserved)),
      reserved: '0',
    })),
    positions: source.positions.map(clonePosition),
    open_orders: [],
    order_history: [],
    recent_fills: [],
    recent_ledger: [],
  };
}

function fillable(order: PaperOrder, bar: MarketBar): boolean {
  const high = finite(bar.high);
  const low = finite(bar.low);
  if (order.order_type === 'market') return true;
  const trigger = finite(order.limit_price ?? order.stop_price);
  if (order.order_type === 'limit') return order.side === 'buy' ? low <= trigger : high >= trigger;
  return order.side === 'buy' ? high >= trigger : low <= trigger;
}

function fillPrice(order: PaperOrder, bar: MarketBar): number {
  if (order.order_type === 'market') return finite(bar.close);
  return finite(order.limit_price ?? order.stop_price);
}

function replaceOrder(snapshot: PaperAccountSnapshot, order: PaperOrder): PaperAccountSnapshot {
  const openOrders = snapshot.open_orders.filter((item) => item.order_id !== order.order_id);
  if (order.status === 'open') openOrders.push(order);
  const orderHistory = (snapshot.order_history ?? []).map((item) => item.order_id === order.order_id ? order : item);
  if (!orderHistory.some((item) => item.order_id === order.order_id)) orderHistory.push(order);
  return { ...snapshot, open_orders: openOrders, order_history: orderHistory };
}

function rejection(snapshot: PaperAccountSnapshot, order: PaperOrder, reason: string): ReplayResult {
  const rejected = { ...order, status: 'rejected' as const, rejection_reason: reason, updated_at: order.created_at };
  return { snapshot: replaceOrder(snapshot, rejected), order: rejected };
}

function applyFill(snapshot: PaperAccountSnapshot, order: PaperOrder, bar: MarketBar): ReplayResult {
  const balance = accountBalance(snapshot);
  const quantity = finite(order.quantity);
  const price = fillPrice(order, bar);
  const notional = quantity * price;
  const commission = notional * Math.max(0, finite(snapshot.account.commission_bps)) / 10_000;
  const position = positionFor(snapshot, order.instrument_id);
  const positionQuantity = finite(position?.quantity);
  if (!balance || quantity <= 0 || price <= 0) return rejection(snapshot, order, 'invalid_replay_price');
  if (order.side === 'buy' && finite(balance.available) < notional + commission) {
    return rejection(snapshot, order, 'insufficient_paper_cash');
  }
  if (order.side === 'sell' && positionQuantity < quantity) {
    return rejection(snapshot, order, 'insufficient_paper_position');
  }

  const now = timestamp(bar);
  let nextPosition: PaperPosition | null = position ? clonePosition(position) : null;
  let realizedPnl = 0;
  if (order.side === 'buy') {
    const oldCost = positionQuantity * finite(position?.average_cost);
    const nextQuantity = positionQuantity + quantity;
    nextPosition = {
      instrument_id: order.instrument_id,
      quantity: decimal(nextQuantity),
      average_cost: decimal((oldCost + notional) / nextQuantity),
      realized_pnl: position?.realized_pnl ?? '0',
      last_price: decimal(price),
      unrealized_pnl: '0',
    };
  } else if (position) {
    realizedPnl = (price - finite(position.average_cost)) * quantity;
    const nextQuantity = positionQuantity - quantity;
    nextPosition = nextQuantity > 0 ? {
      ...position,
      quantity: decimal(nextQuantity),
      last_price: decimal(price),
      realized_pnl: decimal(finite(position.realized_pnl) + realizedPnl),
      unrealized_pnl: '0',
    } : null;
  }

  const nextOrder: PaperOrder = {
    ...order,
    status: 'filled',
    filled_quantity: decimal(quantity),
    average_fill_price: decimal(price),
    reference_price: order.reference_price ?? decimal(price),
    updated_at: now,
  };
  const reservation = order.side === 'buy' && order.order_type !== 'market'
    ? quantity * finite(order.limit_price ?? order.stop_price)
    : 0;
  const balanceDelta = order.side === 'buy'
    ? -(notional + commission) + reservation
    : notional - commission;
  const nextBalances = snapshot.balances.map((item) => item.currency === balance.currency
    ? { ...item, available: decimal(finite(item.available) + balanceDelta), reserved: decimal(Math.max(0, finite(item.reserved) - reservation)) }
    : item);
  const nextPositions = snapshot.positions.filter((item) => item.instrument_id !== order.instrument_id);
  if (nextPosition) nextPositions.push(nextPosition);
  const fill: PaperFill = {
    fill_id: `replay-fill-${order.order_id}`,
    order_id: order.order_id,
    instrument_id: order.instrument_id,
    side: order.side,
    quantity: decimal(quantity),
    price: decimal(price),
    commission: decimal(commission),
    source_time: now,
    evaluated_at: now,
    idempotency_key: order.idempotency_key,
  };
  const ledger: PaperLedgerEntry[] = [
    {
      ledger_id: `replay-ledger-${order.order_id}-trade`,
      entry_type: 'trade_cash',
      currency: balance.currency,
      amount: decimal(order.side === 'buy' ? -notional : notional),
      order_id: order.order_id,
      fill_id: fill.fill_id,
      idempotency_key: `${order.idempotency_key}-trade`,
      payload: { replay: true, price: decimal(price) },
      created_at: now,
    },
    {
      ledger_id: `replay-ledger-${order.order_id}-commission`,
      entry_type: 'commission',
      currency: balance.currency,
      amount: decimal(-commission),
      order_id: order.order_id,
      fill_id: fill.fill_id,
      idempotency_key: `${order.idempotency_key}-commission`,
      payload: { replay: true },
      created_at: now,
    },
  ];
  if (realizedPnl !== 0) ledger.push({
    ledger_id: `replay-ledger-${order.order_id}-pnl`,
    entry_type: 'realized_pnl',
    currency: balance.currency,
    amount: decimal(realizedPnl),
    order_id: order.order_id,
    fill_id: fill.fill_id,
    idempotency_key: `${order.idempotency_key}-pnl`,
    payload: { replay: true },
    created_at: now,
  });
  const nextSnapshot = replaceOrder({
    ...snapshot,
    balances: nextBalances,
    positions: nextPositions,
    recent_fills: [...snapshot.recent_fills, fill],
    recent_ledger: [...snapshot.recent_ledger, ...ledger],
  }, nextOrder);
  return { snapshot: markToBar(nextSnapshot, bar), order: nextOrder };
}

function addOpenOrder(snapshot: PaperAccountSnapshot, order: PaperOrder, bar: MarketBar): ReplayResult {
  const balance = accountBalance(snapshot);
  const reservation = order.side === 'buy'
    ? finite(order.quantity) * finite(order.limit_price ?? order.stop_price)
    : 0;
  if (balance && reservation > finite(balance.available)) return rejection(snapshot, order, 'insufficient_paper_cash');
  const nextBalances = balance && reservation > 0
    ? snapshot.balances.map((item) => item.currency === balance.currency
      ? { ...item, available: decimal(finite(item.available) - reservation), reserved: decimal(finite(item.reserved) + reservation) }
      : item)
    : snapshot.balances;
  return {
    snapshot: replaceOrder({ ...snapshot, balances: nextBalances }, order),
    order,
  };
}

/** Advance open replay orders using the current historical candle. */
export function advanceReplaySnapshot(source: PaperAccountSnapshot, bar: MarketBar): PaperAccountSnapshot {
  let current = markToBar(source, bar);
  for (const order of [...current.open_orders]) {
    if (!fillable(order, bar)) continue;
    current = applyFill(current, order, bar).snapshot;
  }
  return current;
}

/** Place an order entirely inside the replay snapshot. This never calls the API. */
export function placeReplayOrder(
  source: PaperAccountSnapshot,
  input: PaperOrderInput,
  bar: MarketBar,
): ReplayResult {
  const prepared = advanceReplaySnapshot(source, bar);
  const now = timestamp(bar);
  const order: PaperOrder = {
    account_id: prepared.account.account_id,
    ...input,
    status: 'open',
    filled_quantity: '0',
    created_at: now,
    updated_at: now,
  };
  if (input.order_type === 'market' || fillable(order, bar)) return applyFill(prepared, order, bar);
  return addOpenOrder(prepared, order, bar);
}
