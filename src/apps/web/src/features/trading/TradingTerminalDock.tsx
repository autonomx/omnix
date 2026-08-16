import { useEffect, useMemo, useState } from 'react';
import type {
  PaperAccount,
  PaperAccountSnapshot,
  PaperOrder,
} from './paperTypes';
import { tradingPaperApi } from './tradingPaperApi';
import type { TradingAlert } from './tradingTypes';
import './TradingTerminalDock.css';
import './TradingTerminalDockMinimize.css';

type DockTab = 'positions' | 'orders' | 'history' | 'balance' | 'journal';
type OrderHistoryFilter = 'all' | 'filled' | 'cancelled' | 'rejected';

const tabs: Array<{ id: DockTab; label: string }> = [
  { id: 'positions', label: 'Positions' },
  { id: 'orders', label: 'Orders' },
  { id: 'history', label: 'Order history' },
  { id: 'balance', label: 'Balance history' },
  { id: 'journal', label: 'Trading journal' },
];

function symbol(instrumentId: string): string {
  const parts = instrumentId.split(':');
  return parts[parts.length - 1] || instrumentId;
}

function number(value?: string | null, digits = 2): string {
  if (value === undefined || value === null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString(undefined, { maximumFractionDigits: digits })
    : String(value);
}

function orderPrice(order: PaperOrder): string {
  if (order.average_fill_price !== undefined && order.average_fill_price !== null) {
    return number(order.average_fill_price);
  }
  if (order.order_type === 'market') return order.status === 'open' ? 'Market' : '—';
  return number(order.limit_price ?? order.stop_price);
}

function signedClass(value?: string | null): string {
  return Number(value ?? 0) < 0 ? 'negative' : 'positive';
}

function orderTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : '—';
}

export function TradingTerminalDock({
  instrumentId,
  bindingId,
  preferredAccountId,
  onAccountChange,
}: {
  instrumentId: string;
  bindingId: string | null;
  preferredAccountId?: string | null;
  onAccountChange?: (accountId: string) => void;
  onSelectAlert?: (alert: TradingAlert) => void;
}) {
  const [tab, setTab] = useState<DockTab>('positions');
  const [historyFilter, setHistoryFilter] = useState<OrderHistoryFilter>('all');
  const [minimized, setMinimized] = useState(true);
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState(preferredAccountId ?? '');
  const [snapshot, setSnapshot] = useState<PaperAccountSnapshot | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');

  const activeAccount = useMemo(
    () => accounts.find((account) => account.account_id === accountId) ?? accounts[0] ?? null,
    [accountId, accounts],
  );
  const positions = snapshot?.positions.filter((position) => Number(position.quantity) !== 0) ?? [];
  const orderHistory = snapshot?.order_history ?? snapshot?.open_orders ?? [];
  const commissionByOrder = useMemo(() => {
    const commissions = new Map<string, string>();
    for (const fill of snapshot?.recent_fills ?? []) {
      const current = Number(commissions.get(fill.order_id) ?? 0);
      commissions.set(fill.order_id, String(current + Number(fill.commission)));
    }
    return commissions;
  }, [snapshot?.recent_fills]);
  const filteredOrderHistory = useMemo(
    () => historyFilter === 'all'
      ? orderHistory
      : orderHistory.filter((order) => order.status === historyFilter),
    [historyFilter, orderHistory],
  );
  const historyCounts = useMemo(() => ({
    all: orderHistory.length,
    filled: orderHistory.filter((order) => order.status === 'filled').length,
    cancelled: orderHistory.filter((order) => order.status === 'cancelled').length,
    rejected: orderHistory.filter((order) => order.status === 'rejected').length,
  }), [orderHistory]);

  const downloadOrderHistory = () => {
    const header = ['Symbol', 'Side', 'Type', 'Quantity', 'Limit price', 'Stop price', 'Fill price', 'Status', 'Commission', 'Placing time', 'Closing time', 'Order ID'];
    const rows = orderHistory.map((order) => [
      symbol(order.instrument_id),
      order.side,
      order.order_type,
      order.quantity,
      order.limit_price ?? '',
      order.stop_price ?? '',
      order.average_fill_price ?? '',
      order.status,
      commissionByOrder.get(order.order_id) ?? '',
      order.created_at ?? '',
      order.updated_at ?? '',
      order.order_id,
    ]);
    const csv = [header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'paper-order-history.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const refresh = async (preferredId?: string) => {
    try {
      const nextAccounts = await tradingPaperApi.accounts();
      setAccounts(nextAccounts);
      const retainedId = nextAccounts.some((account) => account.account_id === accountId) ? accountId : '';
      const nextId = preferredId || preferredAccountId || retainedId || nextAccounts[0]?.account_id || '';
      setAccountId(nextId);
      onAccountChange?.(nextId);
      setSnapshot(nextId ? await tradingPaperApi.snapshot(nextId) : null);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    void refresh(preferredAccountId ?? undefined);
  }, [preferredAccountId]);

  useEffect(() => {
    if (!accountId) return;
    const timer = window.setInterval(() => void refresh(accountId), 5_000);
    return () => window.clearInterval(timer);
  }, [accountId]);

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
      aria-label="Paper trading activity"
      data-status={status}
    >
      <div className="trading-dock-main">
        <nav role="tablist" aria-label="Paper trading activity">
          {tabs.map((item) => {
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            );
          })}
          <span className="trading-dock-status">Paper only · {status}</span>
          <button type="button" className="trading-dock-download" aria-label="Download order history" title="Download order history" onClick={downloadOrderHistory}>⇩</button>
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
          {!snapshot ? (
            <div className="trading-dock-empty">
              <strong>No paper account</strong>
              <span>Open the Trade tab to create an account and begin simulation.</span>
            </div>
          ) : null}

          {snapshot && tab === 'positions' ? (
            <div className="trading-dock-table-scroll"><table>
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
            </table></div>
          ) : null}

          {snapshot && tab === 'orders' ? (
            <div className="trading-dock-table-scroll"><table>
              <thead><tr><th>Symbol</th><th>Side</th><th>Type</th><th>Quantity</th><th>Price</th><th>Status</th><th /></tr></thead>
              <tbody>
                {snapshot.open_orders.map((order) => (
                  <tr key={order.order_id}>
                    <td><strong>{symbol(order.instrument_id)}</strong></td>
                    <td className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side}</td>
                    <td>{order.order_type}</td>
                    <td>{number(order.quantity, 6)}</td>
                    <td>{orderPrice(order)}</td>
                    <td>{order.status}</td>
                    <td><button type="button" onClick={() => void cancelOrder(order.order_id)}>Cancel</button></td>
                  </tr>
                ))}
                {snapshot.open_orders.length === 0 ? <tr><td colSpan={7}>No open orders.</td></tr> : null}
              </tbody>
            </table></div>
          ) : null}

          {snapshot && tab === 'history' ? (
            <>
              <nav className="trading-order-history-filters" role="tablist" aria-label="Order history filters">
                {(['all', 'filled', 'cancelled', 'rejected'] as OrderHistoryFilter[]).map((filter) => (
                  <button key={filter} type="button" role="tab" aria-selected={historyFilter === filter} onClick={() => setHistoryFilter(filter)}>
                    {filter[0].toUpperCase() + filter.slice(1)} <span>{historyCounts[filter]}</span>
                  </button>
                ))}
              </nav>
              <div className="trading-dock-table-scroll"><table className="trading-order-history-table">
                <thead><tr><th>Symbol</th><th>Side</th><th>Type</th><th>Quantity</th><th>Limit price</th><th>Stop price</th><th>Fill price</th><th>Status</th><th>Commission</th><th>Placing time</th><th>Closing time</th><th>Order ID</th><th>Level ID</th><th>Leverage</th><th>Margin</th></tr></thead>
                <tbody>
                  {filteredOrderHistory.map((order) => (
                    <tr key={order.order_id}>
                      <td><strong>{symbol(order.instrument_id)}</strong></td>
                      <td className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side}</td>
                      <td>{order.order_type}</td>
                      <td>{number(order.quantity, 6)}</td>
                      <td>{number(order.limit_price)}</td>
                      <td>{number(order.stop_price)}</td>
                      <td>{orderPrice(order)}</td>
                      <td className={order.status === 'rejected' ? 'negative' : order.status === 'filled' ? 'positive' : undefined}>{order.status}</td>
                      <td>{number(commissionByOrder.get(order.order_id))}</td>
                      <td>{orderTime(order.created_at)}</td>
                      <td>{order.status === 'open' ? '—' : orderTime(order.updated_at)}</td>
                      <td><code>{order.order_id}</code></td>
                      <td>—</td>
                      <td>—</td>
                      <td>—</td>
                    </tr>
                  ))}
                  {filteredOrderHistory.length === 0 ? <tr><td colSpan={15}>No orders in this filter.</td></tr> : null}
                </tbody>
              </table></div>
            </>
          ) : null}

          {snapshot && tab === 'balance' ? (
            <div className="trading-dock-table-scroll"><table>
              <thead><tr><th>Time</th><th>Type</th><th>Currency</th><th>Amount</th><th>Order ID</th><th>Fill ID</th><th>Evidence</th></tr></thead>
              <tbody>
                {snapshot.recent_ledger.map((entry) => (
                  <tr key={entry.ledger_id}>
                    <td>{orderTime(entry.created_at)}</td>
                    <td>{entry.entry_type}</td>
                    <td>{entry.currency}</td>
                    <td className={signedClass(entry.amount)}>{number(entry.amount)}</td>
                    <td>{entry.order_id ?? '—'}</td>
                    <td>{entry.fill_id ?? '—'}</td>
                    <td><code>{entry.idempotency_key.slice(0, 18)}</code></td>
                  </tr>
                ))}
                {snapshot.recent_ledger.length === 0 ? <tr><td colSpan={7}>No balance history yet.</td></tr> : null}
              </tbody>
            </table></div>
          ) : null}

          {snapshot && tab === 'journal' ? (
            <div className="trading-dock-table-scroll"><table>
              <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Quantity</th><th>Fill price</th><th>Commission</th><th>Order ID</th></tr></thead>
              <tbody>
                {snapshot.recent_fills.map((fill) => (
                  <tr key={fill.fill_id}>
                    <td>{orderTime(fill.source_time)}</td>
                    <td><strong>{symbol(fill.instrument_id)}</strong></td>
                    <td className={fill.side === 'buy' ? 'positive' : 'negative'}>{fill.side}</td>
                    <td>{number(fill.quantity, 6)}</td>
                    <td>{number(fill.price)}</td>
                    <td>{number(fill.commission)}</td>
                    <td><code>{fill.order_id}</code></td>
                  </tr>
                ))}
                {snapshot.recent_fills.length === 0 ? <tr><td colSpan={7}>No journal entries yet.</td></tr> : null}
              </tbody>
            </table></div>
          ) : null}
        </div> : null}
      </div>

    </section>
  );
}
