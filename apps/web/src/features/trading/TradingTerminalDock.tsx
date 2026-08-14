import { useEffect, useMemo, useState } from 'react';
import { TradingAlertsPanel } from './TradingAlertsPanel';
import type { PaperAccount, PaperAccountSnapshot, PaperOrderType, PaperSide } from './paperTypes';
import { tradingPaperApi } from './tradingPaperApi';
import './TradingTerminalDock.css';
import './TradingTerminalDockMinimize.css';

type DockTab = 'positions' | 'orders' | 'alerts' | 'history' | 'logs';

const tabs: Array<{ id: DockTab; label: string }> = [
  { id: 'positions', label: 'Positions' },
  { id: 'orders', label: 'Orders' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'history', label: 'Trade history' },
  { id: 'logs', label: 'Logs' },
];

function symbol(instrumentId: string): string {
  const parts = instrumentId.split(':');
  return parts[parts.length - 1] || instrumentId;
}

function number(value?: string | null, digits = 2): string {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString(undefined, { maximumFractionDigits: digits })
    : String(value ?? '—');
}

function signedClass(value?: string | null): string {
  return Number(value ?? 0) < 0 ? 'negative' : 'positive';
}

export function TradingTerminalDock({
  instrumentId,
  bindingId,
}: {
  instrumentId: string;
  bindingId: string | null;
}) {
  const [tab, setTab] = useState<DockTab>('positions');
  const [minimized, setMinimized] = useState(true);
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState('');
  const [snapshot, setSnapshot] = useState<PaperAccountSnapshot | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');
  const [orderType, setOrderType] = useState<PaperOrderType>('market');
  const [quantity, setQuantity] = useState('1');
  const [triggerPrice, setTriggerPrice] = useState('');
  const [initialCash, setInitialCash] = useState('100000');

  const activeAccount = useMemo(
    () => accounts.find((account) => account.account_id === accountId) ?? accounts[0] ?? null,
    [accountId, accounts],
  );
  const positions = snapshot?.positions.filter((position) => Number(position.quantity) !== 0) ?? [];

  const refresh = async (preferredId?: string) => {
    try {
      const nextAccounts = await tradingPaperApi.accounts();
      setAccounts(nextAccounts);
      const retainedId = nextAccounts.some((account) => account.account_id === accountId) ? accountId : '';
      const nextId = preferredId || retainedId || nextAccounts[0]?.account_id || '';
      setAccountId(nextId);
      setSnapshot(nextId ? await tradingPaperApi.snapshot(nextId) : null);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!accountId) return;
    const timer = window.setInterval(() => void refresh(accountId), 5_000);
    return () => window.clearInterval(timer);
  }, [accountId]);

  const createAccount = async () => {
    const cash = Number(initialCash);
    if (!Number.isFinite(cash) || cash < 0) {
      setStatus('error');
      return;
    }
    const nextId = `paper-terminal-${Date.now()}`;
    setStatus('saving');
    try {
      await tradingPaperApi.createAccount({
        account_id: nextId,
        name: `Paper Account ${accounts.length + 1}`,
        base_currency: 'USD',
        initial_cash: initialCash,
        commission_bps: '0',
      });
      await refresh(nextId);
    } catch {
      setStatus('error');
    }
  };

  const placeOrder = async (side: PaperSide) => {
    if (!activeAccount?.enabled) return;
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
    setStatus('saving');
    try {
      await tradingPaperApi.placeOrder(activeAccount.account_id, {
        order_id: orderId,
        instrument_id: instrumentId,
        binding_id: bindingId,
        side,
        order_type: orderType,
        quantity,
        limit_price: orderType === 'limit' ? triggerPrice : null,
        stop_price: orderType === 'stop' ? triggerPrice : null,
        idempotency_key: orderId,
      });
      await refresh(activeAccount.account_id);
      setTab('orders');
    } catch {
      setStatus('error');
    }
  };

  const cancelOrder = async (orderId: string) => {
    if (!activeAccount) return;
    setStatus('saving');
    try {
      await tradingPaperApi.cancelOrder(activeAccount.account_id, orderId);
      await refresh(activeAccount.account_id);
    } catch {
      setStatus('error');
    }
  };

  return (
    <section
      className={`trading-terminal-dock${minimized ? ' is-minimized' : ''}`}
      aria-label="Paper positions and order entry"
      data-status={status}
    >
      <div className="trading-dock-main">
        <nav role="tablist" aria-label="Paper trading activity">
          {tabs.map((item) => {
            const count = item.id === 'positions'
              ? positions.length
              : item.id === 'orders'
                ? snapshot?.open_orders.length ?? 0
                : item.id === 'history'
                  ? snapshot?.recent_fills.length ?? 0
                  : null;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {item.label}{count === null ? '' : ` (${count})`}
              </button>
            );
          })}
          <span className="trading-dock-status">Paper only · {status}</span>
          <button
            type="button"
            className="trading-dock-toggle"
            aria-label={minimized ? 'Restore paper trading panel' : 'Minimize paper trading panel'}
            aria-expanded={!minimized}
            onClick={() => setMinimized((current) => !current)}
          >
            {minimized ? 'Show' : 'Minimize'}
          </button>
        </nav>

        {!minimized ? <div className="trading-dock-content" role="tabpanel" tabIndex={0}>
          {!snapshot && tab !== 'alerts' ? (
            <div className="trading-dock-empty">
              <strong>No paper account</strong>
              <span>Create an account in the order ticket to begin simulation.</span>
            </div>
          ) : null}

          {snapshot && tab === 'positions' ? (
            <table>
              <thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Avg. price</th><th>Mark price</th><th>P&amp;L</th><th>Status</th></tr></thead>
              <tbody>
                {positions.map((position) => {
                  const pnl = Number(position.realized_pnl) + Number(position.unrealized_pnl);
                  return (
                    <tr key={position.instrument_id}>
                      <td><strong>{symbol(position.instrument_id)}</strong></td>
                      <td className="positive">Long</td>
                      <td>{number(position.quantity, 6)}</td>
                      <td>{number(position.average_cost)}</td>
                      <td>{number(position.last_price)}</td>
                      <td className={signedClass(String(pnl))}>{number(String(pnl))}</td>
                      <td className="positive">Open</td>
                    </tr>
                  );
                })}
                {positions.length === 0 ? <tr><td colSpan={7}>No open positions.</td></tr> : null}
              </tbody>
            </table>
          ) : null}

          {snapshot && tab === 'orders' ? (
            <table>
              <thead><tr><th>Symbol</th><th>Side</th><th>Type</th><th>Quantity</th><th>Trigger</th><th>Status</th><th /></tr></thead>
              <tbody>
                {snapshot.open_orders.map((order) => (
                  <tr key={order.order_id}>
                    <td><strong>{symbol(order.instrument_id)}</strong></td>
                    <td className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side}</td>
                    <td>{order.order_type}</td>
                    <td>{number(order.quantity, 6)}</td>
                    <td>{number(order.limit_price ?? order.stop_price)}</td>
                    <td>{order.status}</td>
                    <td><button type="button" onClick={() => void cancelOrder(order.order_id)}>Cancel</button></td>
                  </tr>
                ))}
                {snapshot.open_orders.length === 0 ? <tr><td colSpan={7}>No open orders.</td></tr> : null}
              </tbody>
            </table>
          ) : null}

          {tab === 'alerts' ? (
            <TradingAlertsPanel instrumentId={instrumentId} bindingId={bindingId} />
          ) : null}

          {snapshot && tab === 'history' ? (
            <table>
              <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Quantity</th><th>Fill price</th><th>Commission</th></tr></thead>
              <tbody>
                {snapshot.recent_fills.map((fill) => (
                  <tr key={fill.fill_id}>
                    <td>{new Date(fill.source_time).toLocaleString()}</td>
                    <td><strong>{symbol(fill.instrument_id)}</strong></td>
                    <td className={fill.side === 'buy' ? 'positive' : 'negative'}>{fill.side}</td>
                    <td>{number(fill.quantity, 6)}</td>
                    <td>{number(fill.price)}</td>
                    <td>{number(fill.commission)}</td>
                  </tr>
                ))}
                {snapshot.recent_fills.length === 0 ? <tr><td colSpan={6}>No fills yet.</td></tr> : null}
              </tbody>
            </table>
          ) : null}

          {snapshot && tab === 'logs' ? (
            <table>
              <thead><tr><th>Type</th><th>Currency</th><th>Amount</th><th>Order</th><th>Evidence</th></tr></thead>
              <tbody>
                {snapshot.recent_ledger.map((entry) => (
                  <tr key={entry.ledger_id}>
                    <td>{entry.entry_type}</td>
                    <td>{entry.currency}</td>
                    <td className={signedClass(entry.amount)}>{number(entry.amount)}</td>
                    <td>{entry.order_id ?? '—'}</td>
                    <td><code>{entry.idempotency_key.slice(0, 18)}</code></td>
                  </tr>
                ))}
                {snapshot.recent_ledger.length === 0 ? <tr><td colSpan={5}>No ledger activity yet.</td></tr> : null}
              </tbody>
            </table>
          ) : null}
        </div> : null}
      </div>

      {!minimized ? <aside className="trading-order-ticket" aria-label="Paper order ticket">
        <header>
          <select
            aria-label="Paper account"
            value={activeAccount?.account_id ?? ''}
            onChange={(event) => void refresh(event.target.value)}
          >
            {accounts.map((account) => (
              <option key={account.account_id} value={account.account_id}>{account.name}</option>
            ))}
          </select>
          <span>Simulation</span>
        </header>

        {!activeAccount ? (
          <div className="trading-create-paper-account">
            <label>Starting cash<input inputMode="decimal" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} /></label>
            <button type="button" onClick={() => void createAccount()}>Create paper account</button>
          </div>
        ) : (
          <>
            <div className="trading-order-ticket-row">
              <strong>{symbol(instrumentId)}</strong>
              <select value={orderType} onChange={(event) => setOrderType(event.target.value as PaperOrderType)} aria-label="Order type">
                <option value="market">Market</option>
                <option value="limit">Limit</option>
                <option value="stop">Stop</option>
              </select>
            </div>
            <label>Quantity<input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>
            {orderType !== 'market' ? (
              <label>{orderType === 'limit' ? 'Limit price' : 'Stop price'}<input inputMode="decimal" value={triggerPrice} onChange={(event) => setTriggerPrice(event.target.value)} /></label>
            ) : null}
            <div className="trading-order-buttons">
              <button type="button" className="buy" disabled={status === 'saving' || !activeAccount.enabled} onClick={() => void placeOrder('buy')}>Buy / Long</button>
              <button type="button" className="sell" disabled={status === 'saving' || !activeAccount.enabled} onClick={() => void placeOrder('sell')}>Sell / Close</button>
            </div>
            <dl>
              <div><dt>Cash</dt><dd>{number(snapshot?.balances[0]?.available)} {activeAccount.base_currency}</dd></div>
              <div><dt>Open positions</dt><dd>{positions.length}</dd></div>
              <div><dt>Open orders</dt><dd>{snapshot?.open_orders.length ?? 0}</dd></div>
            </dl>
            <small>Long-only paper model. No leverage and no live brokerage execution.</small>
          </>
        )}
      </aside> : null}
    </section>
  );
}
