import { useEffect, useMemo, useState } from 'react';
import type { PaperAccount, PaperOrderType, PaperSide } from './paperTypes';
import { tradingPaperApi } from './tradingPaperApi';
import './TradingPaper.css';

export function TradingPaperPanel({
  instrumentId,
  bindingId,
}: {
  instrumentId: string;
  bindingId: string | null;
}) {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState('');
  const [snapshot, setSnapshot] = useState<Awaited<ReturnType<typeof tradingPaperApi.snapshot>> | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'conflict' | 'error'>('loading');
  const [initialCash, setInitialCash] = useState('100000');
  const [side, setSide] = useState<PaperSide>('buy');
  const [orderType, setOrderType] = useState<PaperOrderType>('market');
  const [quantity, setQuantity] = useState('1');
  const [triggerPrice, setTriggerPrice] = useState('');

  const activeAccount = useMemo(
    () => accounts.find((account) => account.account_id === accountId) ?? accounts[0] ?? null,
    [accountId, accounts],
  );

  const refresh = async (preferredId?: string) => {
    try {
      const nextAccounts = await tradingPaperApi.accounts();
      setAccounts(nextAccounts);
      const nextId = preferredId
        ?? (nextAccounts.some((account) => account.account_id === accountId) ? accountId : nextAccounts[0]?.account_id)
        ?? '';
      setAccountId(nextId);
      setSnapshot(nextId ? await tradingPaperApi.snapshot(nextId) : null);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (accountId) void refresh(accountId);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [accountId]);

  const mutate = async (operation: () => Promise<unknown>, preferredId?: string) => {
    setStatus('saving');
    try {
      await operation();
      await refresh(preferredId);
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
    }
  };

  const createAccount = async () => {
    const cash = Number(initialCash);
    if (!Number.isFinite(cash) || cash < 0) {
      setStatus('error');
      return;
    }
    const id = `paper-${Date.now()}`;
    await mutate(
      () => tradingPaperApi.createAccount({
        account_id: id,
        name: `Paper Account ${accounts.length + 1}`,
        base_currency: 'USD',
        initial_cash: initialCash,
        commission_bps: '0',
      }),
      id,
    );
  };

  const placeOrder = async () => {
    if (!activeAccount || !activeAccount.enabled) return;
    const numericQuantity = Number(quantity);
    const numericTrigger = Number(triggerPrice);
    if (!Number.isFinite(numericQuantity) || numericQuantity <= 0) {
      setStatus('error');
      return;
    }
    if (orderType !== 'market' && (!Number.isFinite(numericTrigger) || numericTrigger <= 0)) {
      setStatus('error');
      return;
    }
    const orderId = `paper-order-${Date.now()}`;
    await mutate(
      () => tradingPaperApi.placeOrder(activeAccount.account_id, {
        order_id: orderId,
        instrument_id: instrumentId,
        binding_id: bindingId,
        side,
        order_type: orderType,
        quantity,
        limit_price: orderType === 'limit' ? triggerPrice : null,
        stop_price: orderType === 'stop' ? triggerPrice : null,
        idempotency_key: orderId,
      }),
      activeAccount.account_id,
    );
  };

  return (
    <section className="trading-paper-panel" aria-label="Paper simulation" data-status={status}>
      <header>
        <div>
          <strong>Paper simulation</strong>
          <small>No live brokerage execution</small>
        </div>
        <span>{status}</span>
      </header>

      <div className="trading-paper-account-controls">
        <label>
          Account
          <select
            value={activeAccount?.account_id ?? ''}
            onChange={(event) => {
              setAccountId(event.target.value);
              void refresh(event.target.value);
            }}
          >
            {accounts.map((account) => (
              <option key={account.account_id} value={account.account_id}>
                {account.name}{account.enabled ? '' : ' · archived'}
              </option>
            ))}
          </select>
        </label>
        <label>
          Starting cash
          <input inputMode="decimal" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} />
        </label>
        <button type="button" onClick={() => void createAccount()} disabled={status === 'saving'}>
          New account
        </button>
      </div>

      {snapshot ? (
        <>
          <div className="trading-paper-summary" aria-label="Paper account summary">
            <span>Cash <strong>{snapshot.balances[0]?.available ?? '0'} {snapshot.account.base_currency}</strong></span>
            <span>Positions <strong>{snapshot.positions.filter((position) => Number(position.quantity) > 0).length}</strong></span>
            <span>Open orders <strong>{snapshot.open_orders.length}</strong></span>
            <span>Revision <strong>{snapshot.account.revision}</strong></span>
          </div>

          <div className="trading-paper-order-form">
            <label>
              Side
              <select value={side} onChange={(event) => setSide(event.target.value as PaperSide)}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>
            <label>
              Type
              <select value={orderType} onChange={(event) => setOrderType(event.target.value as PaperOrderType)}>
                <option value="market">Market</option>
                <option value="limit">Limit</option>
                <option value="stop">Stop</option>
              </select>
            </label>
            <label>
              Quantity
              <input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
            </label>
            {orderType !== 'market' ? (
              <label>
                {orderType === 'limit' ? 'Limit price' : 'Stop price'}
                <input inputMode="decimal" value={triggerPrice} onChange={(event) => setTriggerPrice(event.target.value)} />
              </label>
            ) : null}
            <button
              type="button"
              disabled={!snapshot.account.enabled || status === 'saving'}
              onClick={() => void placeOrder()}
            >
              Place simulated order
            </button>
          </div>

          <details open>
            <summary>Positions ({snapshot.positions.length})</summary>
            <ul className="trading-paper-list">
              {snapshot.positions.map((position) => (
                <li key={position.instrument_id}>
                  <strong>{position.instrument_id}</strong>
                  <span>{position.quantity} @ {position.average_cost}</span>
                  <small>Realized {position.realized_pnl} · Unrealized {position.unrealized_pnl}</small>
                </li>
              ))}
            </ul>
          </details>

          <details open>
            <summary>Open orders ({snapshot.open_orders.length})</summary>
            <ul className="trading-paper-list">
              {snapshot.open_orders.map((order) => (
                <li key={order.order_id}>
                  <strong>{order.side} {order.quantity} · {order.order_type}</strong>
                  <span>{order.instrument_id}</span>
                  <button
                    type="button"
                    onClick={() => void mutate(
                      () => tradingPaperApi.cancelOrder(snapshot.account.account_id, order.order_id),
                      snapshot.account.account_id,
                    )}
                  >
                    Cancel
                  </button>
                </li>
              ))}
            </ul>
          </details>

          <details>
            <summary>Recent fills ({snapshot.recent_fills.length})</summary>
            <ul className="trading-paper-list">
              {snapshot.recent_fills.slice(0, 20).map((fill) => (
                <li key={fill.fill_id}>
                  <strong>{fill.side} {fill.quantity} @ {fill.price}</strong>
                  <span>{fill.instrument_id}</span>
                  <time dateTime={fill.source_time}>{new Date(fill.source_time).toLocaleString()}</time>
                </li>
              ))}
            </ul>
          </details>

          <div className="trading-paper-danger-actions">
            <button
              type="button"
              onClick={() => void mutate(
                () => tradingPaperApi.resetAccount(snapshot.account, initialCash),
                snapshot.account.account_id,
              )}
            >
              Reset simulation
            </button>
            <button
              type="button"
              disabled={!snapshot.account.enabled}
              onClick={() => void mutate(
                () => tradingPaperApi.archiveAccount(snapshot.account),
                snapshot.account.account_id,
              )}
            >
              Archive account
            </button>
          </div>
        </>
      ) : (
        <p>Create a paper account to simulate orders using canonical Trading instruments.</p>
      )}
    </section>
  );
}
