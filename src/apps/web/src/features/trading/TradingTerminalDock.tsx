import { useEffect, useMemo, useState } from 'react';
import type { PaperAccount, PaperAccountSnapshot, PaperOrder } from './paperTypes';
import { tradingPaperApi } from './tradingPaperApi';
import type { TradingAlert } from './tradingTypes';
import './TradingTerminalDock.css';
import './TradingTerminalDockMinimize.css';
import './TradingTerminalDockLight.css';
import './TradingTerminalDockData.css';

type DockTab = 'positions' | 'orders' | 'history' | 'balance' | 'journal';
type OrderFilter = 'all' | 'working' | 'inactive' | 'filled' | 'cancelled' | 'rejected';
type AccountModal = 'create' | 'settings' | null;
type CommissionType = 'Percent' | 'Fixed';
type Leverage = { stocks: string; futures: string; forex: string; crypto: string; others: string };
type PaperAccountSettings = {
  marginControl: boolean;
  leverage: Leverage;
  futuresOptions: boolean;
  commissionPerContract: string;
  othersCommission: boolean;
  commission: string;
  commissionType: CommissionType;
};
type CreateAccountDraft = PaperAccountSettings & { name: string; balance: string; currency: string };
type DockPosition = PaperAccountSnapshot['positions'][number] & { pending?: boolean; pendingSide?: 'buy' | 'sell'; pendingOrderId?: string };

const tabs: Array<{ id: DockTab; label: string }> = [
  { id: 'positions', label: 'Positions' }, { id: 'orders', label: 'Orders' },
  { id: 'history', label: 'Order history' }, { id: 'balance', label: 'Balance history' },
  { id: 'journal', label: 'Trading journal' },
];
const orderFilters: Array<{ id: OrderFilter; label: string }> = [
  { id: 'all', label: 'All' }, { id: 'working', label: 'Working' }, { id: 'inactive', label: 'Inactive' },
  { id: 'filled', label: 'Filled' }, { id: 'cancelled', label: 'Cancelled' }, { id: 'rejected', label: 'Rejected' },
];
const leverageOptions = ['1:1', '10:1', '20:1', '50:1', '100:1', '500:1'];
const settingsStorageKey = 'omnix.trading.paper-account-settings';

function symbol(instrumentId: string): string {
  const parts = instrumentId.split(':');
  const venue = parts[1] ?? 'Market';
  const raw = parts[parts.length - 1] || instrumentId;
  return `${venue}:${raw.replaceAll('-', '')}`;
}

function quantity(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? Math.abs(parsed).toLocaleString(undefined, { maximumFractionDigits: 6 })
    : String(value);
}

function signedNumber(value?: string | number | null, digits = 2): string {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return '—';
  return `${parsed > 0 ? '+' : ''}${number(String(parsed), digits)}`;
}

function tableTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const pad = (item: number) => String(item).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function MarketBadge({ instrumentId }: { instrumentId: string }) {
  return <span className="trading-market-badge"><span className="trading-market-icon" aria-hidden="true">≋</span><strong>{symbol(instrumentId)}</strong></span>;
}

function number(value?: string | number | null, digits = 2): string {
  if (value === undefined || value === null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: digits })
    : String(value);
}

function signedClass(value?: string | number | null): string {
  return Number(value ?? 0) < 0 ? 'negative' : 'positive';
}

function orderPrice(order: PaperOrder): string {
  if (order.average_fill_price !== undefined && order.average_fill_price !== null) return number(order.average_fill_price);
  if (order.order_type === 'market') return order.status === 'open' ? 'Market' : '—';
  return number(order.limit_price ?? order.stop_price);
}

function rejectionMessage(reason?: string | null): string {
  switch (reason) {
    case 'insufficient_paper_cash': return 'Insufficient available paper cash at the fill price.';
    case 'insufficient_paper_position': return 'Insufficient paper position available to sell.';
    case 'paper_account_disabled': return 'This paper account is disabled.';
    default: return reason ? `Order rejected: ${reason.replaceAll('_', ' ')}` : 'The order was rejected.';
  }
}

function OrderStatus({ order }: { order: PaperOrder }) {
  const label = order.status === 'open' ? 'Working' : order.status[0].toUpperCase() + order.status.slice(1);
  if (order.status !== 'rejected') {
    return <span className={order.status === 'filled' ? 'positive' : undefined}>{label}</span>;
  }
  const tooltipId = `paper-order-rejection-${order.order_id}`;
  const message = rejectionMessage(order.rejection_reason);
  return <span
    className="trading-order-rejected-status"
    tabIndex={0}
    title={message}
    aria-describedby={tooltipId}
  >
    {label}
    <span id={tooltipId} className="trading-order-rejection-tooltip" role="tooltip">{message}</span>
  </span>;
}

function defaultSettings(account?: PaperAccount | null): PaperAccountSettings {
  const commission = account ? Number(account.commission_bps) / 100 : 0.005;
  return {
    marginControl: false,
    leverage: { stocks: '500:1', futures: '500:1', forex: '500:1', crypto: '500:1', others: '500:1' },
    futuresOptions: false, commissionPerContract: '0.01', othersCommission: true,
    commission: Number.isFinite(commission) && commission > 0 ? String(commission) : '0.005', commissionType: 'Percent',
  };
}

function defaultCreateDraft(): CreateAccountDraft {
  return {
    name: '', balance: '100000.00', currency: 'USD', ...defaultSettings(),
    leverage: { stocks: '1:1', futures: '20:1', forex: '50:1', crypto: '10:1', others: '50:1' },
    othersCommission: false,
  };
}

function readStoredSettings(): Record<string, PaperAccountSettings> {
  if (typeof window === 'undefined') return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(settingsStorageKey) ?? '{}');
    return parsed && typeof parsed === 'object' ? parsed as Record<string, PaperAccountSettings> : {};
  } catch { return {}; }
}

function accountIdForName(name: string): string {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);
  return `${slug || 'paper-account'}-${Date.now()}`;
}

export function TradingTerminalDock({
  instrumentId: _instrumentId,
  bindingId: _bindingId,
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
  const [orderFilter, setOrderFilter] = useState<OrderFilter>('all');
  const [minimized, setMinimized] = useState(true);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [modal, setModal] = useState<AccountModal>(null);
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState(preferredAccountId ?? '');
  const [snapshot, setSnapshot] = useState<PaperAccountSnapshot | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');
  const [notice, setNotice] = useState<string | null>(null);
  const [settingsByAccount, setSettingsByAccount] = useState<Record<string, PaperAccountSettings>>(readStoredSettings);
  const [settingsDraft, setSettingsDraft] = useState<PaperAccountSettings>(defaultSettings());
  const [createDraft, setCreateDraft] = useState<CreateAccountDraft>(defaultCreateDraft);

  const activeAccount = useMemo(() => accounts.find((account) => account.account_id === accountId) ?? accounts[0] ?? null, [accountId, accounts]);
  const positions = snapshot?.positions.filter((position) => Number(position.quantity) !== 0) ?? [];
  const orderHistory = snapshot?.order_history ?? snapshot?.open_orders ?? [];
  const displayedPositions = useMemo<DockPosition[]>(() => {
    const actualPositions: DockPosition[] = [...positions];
    for (const order of snapshot?.open_orders ?? []) {
      actualPositions.push({
        instrument_id: order.instrument_id,
        quantity: order.quantity,
        average_cost: order.reference_price ?? order.limit_price ?? order.stop_price ?? '',
        realized_pnl: '0',
        last_price: order.reference_price ?? null,
        unrealized_pnl: '0',
        pending: true,
        pendingSide: order.side,
        pendingOrderId: order.order_id,
      });
    }
    return actualPositions;
  }, [positions, snapshot?.open_orders]);
  const activeSettings = activeAccount ? settingsByAccount[activeAccount.account_id] ?? defaultSettings(activeAccount) : defaultSettings();
  const baseBalance = useMemo(() => snapshot?.balances.find((balance) => balance.currency === activeAccount?.base_currency) ?? snapshot?.balances[0] ?? null, [activeAccount?.base_currency, snapshot?.balances]);
  const realizedPnl = useMemo(() => (snapshot?.positions ?? []).reduce((total, position) => total + Number(position.realized_pnl), 0), [snapshot?.positions]);
  const unrealizedPnl = useMemo(() => (snapshot?.positions ?? []).reduce((total, position) => total + Number(position.unrealized_pnl), 0), [snapshot?.positions]);
  const accountBalance = Number(baseBalance?.available ?? 0) + Number(baseBalance?.reserved ?? 0);
  const equity = accountBalance + unrealizedPnl;
  const ordersMargin = Number(baseBalance?.reserved ?? 0);
  const accountMargin = positions.reduce((total, position) => {
    const leverage = Number.parseFloat(activeSettings.leverage.crypto) || 1;
    return total + (Number(position.average_cost) * Math.abs(Number(position.quantity))) / leverage;
  }, 0);
  const marginBuffer = equity > 0 ? (Number(baseBalance?.available ?? 0) / equity) * 100 : 0;
  const commissionByOrder = useMemo(() => {
    const commissions = new Map<string, string>();
    for (const fill of snapshot?.recent_fills ?? []) commissions.set(fill.order_id, String(Number(commissions.get(fill.order_id) ?? 0) + Number(fill.commission)));
    return commissions;
  }, [snapshot?.recent_fills]);
  const orderCounts = useMemo(() => ({
    all: orderHistory.length, working: orderHistory.filter((order) => order.status === 'open').length, inactive: 0,
    filled: orderHistory.filter((order) => order.status === 'filled').length,
    cancelled: orderHistory.filter((order) => order.status === 'cancelled').length,
    rejected: orderHistory.filter((order) => order.status === 'rejected').length,
  }), [orderHistory]);
  const filteredOrders = useMemo(() => {
    if (orderFilter === 'all') return orderHistory;
    if (orderFilter === 'working') return orderHistory.filter((order) => order.status === 'open');
    if (orderFilter === 'inactive') return [];
    return orderHistory.filter((order) => order.status === orderFilter);
  }, [orderFilter, orderHistory]);
  const historyFilters = orderFilters.filter((filter) => ['all', 'filled', 'cancelled', 'rejected'].includes(filter.id));
  const balanceHistory = useMemo(() => {
    if (!snapshot) return [];
    const ledger = snapshot.recent_ledger;
    const currentCash = Number(baseBalance?.available ?? 0) + Number(baseBalance?.reserved ?? 0);
    const ledgerTotal = ledger.reduce((total, entry) => total + Number(entry.amount), 0);
    const ordersById = new Map(orderHistory.map((order) => [order.order_id, order]));
    const events = [
      ...ledger.filter((entry) => entry.entry_type === 'deposit' && !entry.order_id).map((entry) => ({
        time: entry.created_at,
        delta: Number(entry.amount),
        realized: 0,
        action: `Deposit ${number(entry.amount)} ${entry.currency}`,
      })),
      ...snapshot.recent_fills.map((fill) => {
        const orderEntries = ledger.filter((entry) => entry.order_id === fill.order_id);
        const order = ordersById.get(fill.order_id);
        const realized = orderEntries.filter((entry) => entry.entry_type === 'realized_pnl').reduce((total, entry) => total + Number(entry.amount), 0);
        const delta = orderEntries.reduce((total, entry) => total + Number(entry.amount), 0);
        const action = `${order?.side === 'sell' ? 'Close long position' : 'Open long position'} for symbol ${symbol(fill.instrument_id)} at price ${number(fill.price, 4)} for ${quantity(fill.quantity)} units. Currency: ${fill.order_id ? (baseBalance?.currency ?? activeAccount?.base_currency ?? 'USD') : 'USD'}, rate: 1.000000, point value: 1.000000`;
        return { time: fill.source_time, delta, realized, action };
      }),
    ].sort((left, right) => new Date(left.time ?? 0).getTime() - new Date(right.time ?? 0).getTime());
    let balance = currentCash - ledgerTotal;
    const rows = events.map((event) => {
      const after = balance + event.delta;
      const row = { ...event, before: balance, after };
      balance = after;
      return row;
    });
    return rows.reverse();
  }, [activeAccount?.base_currency, baseBalance?.available, baseBalance?.currency, baseBalance?.reserved, orderHistory, snapshot]);
  const journalEntries = useMemo(() => {
    const fillsByOrder = new Map((snapshot?.recent_fills ?? []).map((fill) => [fill.order_id, fill]));
    return orderHistory.flatMap((order) => {
      const fill = fillsByOrder.get(order.order_id);
      const market = symbol(order.instrument_id);
      const entries = [
        { time: order.created_at, id: `${order.order_id}-placed`, text: `Order ${order.order_id} successfully placed` },
        { time: order.created_at, id: `${order.order_id}-call`, text: `Call to place ${order.order_type} order to ${order.side} ${quantity(order.quantity)} units of symbol ${market}` },
      ];
      if (fill) entries.unshift({ time: fill.source_time, id: `${fill.fill_id}-executed`, text: `Order ${fill.order_id} for symbol ${market} has been executed at price ${number(fill.price, 4)} for ${quantity(fill.quantity)} units` });
      return entries;
    }).sort((left, right) => new Date(right.time ?? 0).getTime() - new Date(left.time ?? 0).getTime());
  }, [orderHistory, snapshot?.recent_fills]);

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
    } catch { setStatus('error'); }
  };

  useEffect(() => { void refresh(preferredAccountId ?? undefined); }, [preferredAccountId]);
  useEffect(() => {
    if (!accountId) return;
    const timer = window.setInterval(() => void refresh(accountId), 5_000);
    return () => window.clearInterval(timer);
  }, [accountId]);
  useEffect(() => {
    if (!modal) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setModal(null); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modal]);

  const selectAccount = (nextId: string) => {
    setAccountMenuOpen(false); setAccountId(nextId); onAccountChange?.(nextId); void refresh(nextId);
  };
  const openSettings = () => {
    if (!activeAccount) return;
    setSettingsDraft(activeSettings); setAccountMenuOpen(false); setNotice(null); setModal('settings');
  };
  const saveSettings = () => {
    if (!activeAccount) return;
    const next = { ...settingsByAccount, [activeAccount.account_id]: settingsDraft };
    setSettingsByAccount(next);
    try { window.localStorage.setItem(settingsStorageKey, JSON.stringify(next)); } catch { /* session-only fallback */ }
    setModal(null); setNotice('Account settings saved for this paper account.');
  };
  const createAccount = async () => {
    const name = createDraft.name.trim(); const balance = Number(createDraft.balance);
    if (!name || !Number.isFinite(balance) || balance < 0) { setNotice('Enter an account name and a valid non-negative balance.'); return; }
    setStatus('saving');
    try {
      const created = await tradingPaperApi.createAccount({
        account_id: accountIdForName(name), name, base_currency: createDraft.currency,
        initial_cash: createDraft.balance,
        commission_bps: createDraft.othersCommission ? String(Number(createDraft.commission) * 100) : '0',
      });
      setAccounts([created.account, ...accounts.filter((account) => account.account_id !== created.account.account_id)]);
      setAccountId(created.account.account_id); setSnapshot(created); onAccountChange?.(created.account.account_id);
      setModal(null); setCreateDraft(defaultCreateDraft()); setStatus('ready'); setNotice(`Created ${created.account.name}.`);
    } catch (error) { setStatus('error'); setNotice(error instanceof Error ? error.message : 'Unable to create paper account.'); }
  };
  const resetAccount = async () => {
    if (!activeAccount || !snapshot) return;
    const deposit = snapshot.recent_ledger.find((entry) => entry.entry_type === 'deposit'); setStatus('saving');
    try {
      const next = await tradingPaperApi.resetAccount(activeAccount, deposit?.amount ?? '100000');
      setSnapshot(next); setAccounts((current) => current.map((account) => account.account_id === next.account.account_id ? next.account : account));
      setStatus('ready'); setModal(null); setNotice('Account reset.');
    } catch (error) { setStatus('error'); setNotice(error instanceof Error ? error.message : 'Unable to reset paper account.'); }
  };
  const archiveAccount = async () => {
    if (!activeAccount) return;
    setStatus('saving');
    try { await tradingPaperApi.archiveAccount(activeAccount); setModal(null); await refresh(); setNotice('Account archived.'); }
    catch (error) { setStatus('error'); setNotice(error instanceof Error ? error.message : 'Unable to archive paper account.'); }
  };
  const downloadOrderHistory = () => {
    const header = ['Symbol', 'Side', 'Type', 'Quantity', 'Limit price', 'Stop price', 'Fill price', 'Status', 'Commission', 'Placing time', 'Closing time', 'Order ID'];
    const rows = orderHistory.map((order) => [symbol(order.instrument_id), order.side, order.order_type, order.quantity, order.limit_price ?? '', order.stop_price ?? '', order.average_fill_price ?? '', order.status, commissionByOrder.get(order.order_id) ?? '', order.created_at ?? '', order.updated_at ?? '', order.order_id]);
    const csv = [header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const link = document.createElement('a');
    link.href = url; link.download = 'paper-order-history.csv'; link.click(); URL.revokeObjectURL(url);
  };

  const renderLeverageField = (label: string, key: keyof Leverage) => (
    <label className="trading-account-field"><span>{label}</span><select value={settingsDraft.leverage[key]} onChange={(event) => setSettingsDraft((current) => ({ ...current, leverage: { ...current.leverage, [key]: event.target.value } }))}>{leverageOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
  );
  const currentForm = modal === 'create' ? createDraft : settingsDraft;
  const setFormValue = <K extends keyof CreateAccountDraft>(key: K, value: CreateAccountDraft[K]) => {
    if (modal === 'create') setCreateDraft((current) => ({ ...current, [key]: value }));
    else if (key in settingsDraft) setSettingsDraft((current) => ({ ...current, [key as keyof PaperAccountSettings]: value } as PaperAccountSettings));
  };

  return (
    <section className={`trading-terminal-dock${minimized ? ' is-minimized' : ''}`} aria-label="Paper trading activity" data-status={status}>
      <div className="trading-dock-main">
        <header className="trading-dock-toolbar">
          <div className="trading-dock-mode"><span className="trading-dock-logo" aria-hidden="true">T</span><strong>Paper Trading</strong><span className="trading-dock-caret" aria-hidden="true">⌄</span></div>
          <div className="trading-dock-account-control">
            <button type="button" className="trading-dock-account-selector" aria-label="Paper trading account" aria-expanded={accountMenuOpen} onClick={() => setAccountMenuOpen((current) => !current)}><span>{activeAccount?.name ?? 'Select account'}</span>{activeAccount ? <small>{activeAccount.base_currency}</small> : null}<span className="trading-dock-caret" aria-hidden="true">{accountMenuOpen ? '⌃' : '⌄'}</span></button>
            {activeAccount ? <button type="button" className="trading-dock-settings-button" aria-label={`Open settings for ${activeAccount.name}`} onClick={openSettings}>⚙</button> : null}
            {accountMenuOpen ? <div className="trading-dock-account-menu" role="menu" aria-label="Paper trading accounts"><span className="trading-dock-account-menu-label">Accounts</span>{accounts.map((account) => <button key={account.account_id} type="button" role="menuitem" className={account.account_id === activeAccount?.account_id ? 'active' : undefined} onClick={() => selectAccount(account.account_id)}><span>{account.name}</span><small>{account.base_currency}</small>{account.account_id === activeAccount?.account_id ? <span aria-hidden="true">✓</span> : null}</button>)}{accounts.length === 0 ? <span className="trading-dock-account-menu-empty">No accounts yet</span> : null}<button type="button" role="menuitem" className="trading-dock-create-account-link" onClick={() => { setAccountMenuOpen(false); setNotice(null); setCreateDraft(defaultCreateDraft()); setModal('create'); }}><span aria-hidden="true">＋</span>Create account…</button></div> : null}
          </div>
          <span className="trading-dock-status">{status === 'error' ? 'Connection error' : 'Paper only'}</span>
          <button type="button" className="trading-dock-download" aria-label="Download order history" title="Download order history" onClick={downloadOrderHistory}>⇩</button>
          <button type="button" className="trading-dock-toggle" aria-label={minimized ? 'Restore paper trading panel' : 'Minimize paper trading panel'} aria-expanded={!minimized} onClick={() => setMinimized((current) => !current)}>{minimized ? 'Show' : 'Minimize'}</button>
        </header>

        {!minimized ? <>
          <div className="trading-dock-summary" aria-label="Paper trading account summary">
            {[['Account balance', accountBalance, activeAccount?.base_currency], ['Equity', equity, activeAccount?.base_currency], ['Realized PnL', realizedPnl, activeAccount?.base_currency], ['Unrealized PnL', unrealizedPnl, activeAccount?.base_currency], ['Account margin', accountMargin, activeAccount?.base_currency], ['Available funds', Number(baseBalance?.available ?? 0), activeAccount?.base_currency], ['Orders margin', ordersMargin, activeAccount?.base_currency], ['Margin buffer', marginBuffer, '%']].map(([label, value, suffix]) => <div key={String(label)} className="trading-dock-summary-item"><span>{label}</span><strong className={label === 'Realized PnL' || label === 'Unrealized PnL' ? signedClass(value as number) : undefined}>{snapshot ? number(value as number) : '—'}{snapshot && suffix ? <small> {suffix}</small> : null}</strong></div>)}
          </div>
          <nav className="trading-dock-tabs" role="tablist" aria-label="Paper trading activity">{tabs.map((item) => <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} onClick={() => { setTab(item.id); if (item.id === 'history' && !historyFilters.some((filter) => filter.id === orderFilter)) setOrderFilter('all'); }}>{item.id === 'positions' && displayedPositions.length > 0 ? `${item.label} ${displayedPositions.length}` : item.label}</button>)}</nav>
          {tab === 'orders' || tab === 'history' ? <nav className="trading-order-filters" role="tablist" aria-label="Order status filters">{(tab === 'orders' ? orderFilters : historyFilters).map((filter) => <button key={filter.id} type="button" role="tab" aria-selected={orderFilter === filter.id} onClick={() => setOrderFilter(filter.id)}>{filter.label}<small>{orderCounts[filter.id]}</small></button>)}</nav> : null}
          <div className={`trading-dock-content${tab === 'history' ? ' trading-dock-content-history' : ''}`} role="tabpanel" tabIndex={0}>
            {!snapshot ? <div className="trading-dock-empty"><strong>No paper account</strong><span>Select an account above or create one to begin simulation.</span><button type="button" onClick={() => { setCreateDraft(defaultCreateDraft()); setModal('create'); }}>Create account</button></div> : null}
            {snapshot && tab === 'positions' ? (
              <div className="trading-dock-table-scroll">
                <table className="trading-positions-table"><thead><tr><th>Symbol</th><th>Side</th><th>Quantity</th><th>Avg fill price</th><th>Take profit</th><th>Stop loss</th><th>Last price</th><th>Unrealized PnL ↑</th><th>Unrealized PnL %</th><th aria-label="Actions" /></tr></thead><tbody>
                  {displayedPositions.map((position) => {
                    const pnl = Number(position.unrealized_pnl);
                    const notional = Number(position.average_cost) * Math.abs(Number(position.quantity));
                    const pnlPercent = notional ? (pnl / notional) * 100 : 0;
                    const side = position.pendingSide === 'sell' ? 'Exit' : position.pending ? 'Long' : Number(position.quantity) < 0 ? 'Short' : 'Long';
                    return <tr key={`${position.instrument_id}-${position.pending ? position.pendingOrderId : 'open'}`}><td><MarketBadge instrumentId={position.instrument_id} /></td><td className="positive">{side}</td><td>{quantity(position.quantity)}</td><td>{number(position.average_cost)}</td><td>—</td><td>—</td><td>{number(position.last_price)}</td><td className={signedClass(pnl)}>{signedNumber(pnl)} <small>{activeAccount?.base_currency}</small></td><td className={signedClass(pnlPercent)}>{signedNumber(pnlPercent)}%</td><td className="trading-row-actions"><span className={position.pending ? 'trading-pending-position' : 'trading-open-position'}>{position.pending ? 'Working' : 'Open'}</span><button type="button" aria-label={`Edit ${symbol(position.instrument_id)} position`}>⌑</button><button type="button" aria-label={`Close ${symbol(position.instrument_id)} position`}>×</button></td></tr>;
                  })}
                  {displayedPositions.length === 0 ? <tr><td colSpan={10}>No open positions.</td></tr> : null}
                </tbody></table>
              </div>
            ) : null}
            {snapshot && tab === 'orders' ? (
              <div className="trading-dock-table-scroll"><table className="trading-orders-table"><thead><tr><th>Symbol</th><th>Type</th><th>Quantity</th><th>Limit price</th><th>Stop price</th><th>Fill price</th><th>Take profit</th><th>Stop loss</th><th>Instruction</th><th>Status</th></tr></thead><tbody>
                {filteredOrders.map((order) => <tr key={order.order_id}><td><MarketBadge instrumentId={order.instrument_id} /></td><td>{order.order_type[0].toUpperCase() + order.order_type.slice(1)}</td><td>{quantity(order.filled_quantity !== '0' ? order.filled_quantity : order.quantity)}</td><td>{number(order.limit_price)}</td><td>{number(order.stop_price)}</td><td>{orderPrice(order)}</td><td>—</td><td>—</td><td className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side === 'buy' ? 'Buy' : 'Sell'}</td><td className={order.status === 'rejected' ? 'negative' : undefined}><OrderStatus order={order} /></td></tr>)}
                {filteredOrders.length === 0 ? <tr><td colSpan={10}>No orders in this filter.</td></tr> : null}
              </tbody></table></div>
            ) : null}
            {snapshot && tab === 'history' ? (
              <div className="trading-dock-table-scroll trading-order-history-scroll"><table className="trading-order-history-table"><thead><tr><th>Symbol</th><th>Side</th><th>Type</th><th>Quantity</th><th>Limit price</th><th>Stop price</th><th>Fill price</th><th>Status</th><th>Commission</th><th>Placing time ↓</th><th>Closing time</th><th>Order ID</th><th>Level ID</th><th>Leverage</th><th>Margin</th></tr></thead><tbody>
                {filteredOrders.map((order) => <tr key={order.order_id}><td><MarketBadge instrumentId={order.instrument_id} /></td><td className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side === 'buy' ? 'Buy' : 'Sell'}</td><td>{order.order_type[0].toUpperCase() + order.order_type.slice(1)}</td><td>{quantity(order.quantity)}</td><td>{number(order.limit_price)}</td><td>{number(order.stop_price)}</td><td>{orderPrice(order)}</td><td className={order.status === 'rejected' ? 'negative' : undefined}><OrderStatus order={order} /></td><td>{number(commissionByOrder.get(order.order_id))}</td><td>{tableTime(order.created_at)}</td><td>{order.status === 'open' ? '—' : tableTime(order.updated_at)}</td><td>{order.order_id}</td><td>—</td><td>{activeSettings.leverage.crypto}</td><td>{number(String(Number(order.quantity) * Number(order.average_fill_price ?? order.limit_price ?? order.stop_price ?? 0) / Math.max(1, Number.parseFloat(activeSettings.leverage.crypto))))} <small>{activeAccount?.base_currency}</small></td></tr>)}
                {filteredOrders.length === 0 ? <tr><td colSpan={15}>No orders in this filter.</td></tr> : null}
              </tbody></table></div>
            ) : null}
            {snapshot && tab === 'balance' ? <div className="trading-dock-table-scroll"><table className="trading-balance-history-table"><thead><tr><th>Time</th><th>Balance before</th><th>Balance after</th><th>Realized PnL</th><th>Action</th></tr></thead><tbody>{balanceHistory.map((entry, index) => <tr key={`${entry.time ?? 'balance'}-${index}`}><td>{tableTime(entry.time)}</td><td>{number(entry.before)}</td><td>{number(entry.after)}</td><td className={signedClass(entry.realized)}>{signedNumber(entry.realized)} <small>{activeAccount?.base_currency}</small></td><td className="trading-action-cell">{entry.action}</td></tr>)}{balanceHistory.length === 0 ? <tr><td colSpan={5}>No balance history yet.</td></tr> : null}</tbody></table></div> : null}
            {snapshot && tab === 'journal' ? <div className="trading-dock-table-scroll"><table className="trading-journal-table"><thead><tr><th>Time</th><th>Text</th></tr></thead><tbody>{journalEntries.map((entry) => <tr key={entry.id}><td>{tableTime(entry.time)}</td><td className="trading-journal-text">{entry.text}</td></tr>)}{journalEntries.length === 0 ? <tr><td colSpan={2}>No journal entries yet.</td></tr> : null}</tbody></table></div> : null}
          </div>
        </> : null}
      </div>
      {notice ? <div className="trading-dock-notice" role="status" aria-live="polite">{notice}</div> : null}

      {modal ? <div className="trading-account-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setModal(null); }}><section className="trading-account-modal" role="dialog" aria-modal="true" aria-labelledby="trading-account-modal-title">
        <header><h2 id="trading-account-modal-title">{modal === 'create' ? 'Create account' : 'Account settings'}</h2><button type="button" aria-label="Close account dialog" onClick={() => setModal(null)}>×</button></header>
        <div className="trading-account-modal-body">
          {modal === 'create' ? <><label className="trading-account-field trading-account-field-wide"><span>Account name</span><input autoFocus value={createDraft.name} onChange={(event) => setFormValue('name', event.target.value)} /></label><div className="trading-account-field-grid"><label className="trading-account-field"><span>Balance</span><input inputMode="decimal" value={createDraft.balance} onChange={(event) => setFormValue('balance', event.target.value)} /></label><label className="trading-account-field"><span>Currency</span><select value={createDraft.currency} onChange={(event) => setFormValue('currency', event.target.value)}><option>USD</option><option>CAD</option><option>EUR</option><option>GBP</option></select></label></div></> : <label className="trading-account-field trading-account-field-wide"><span>Account name</span><input value={activeAccount?.name ?? ''} readOnly /></label>}
          <fieldset><legend>Leverage</legend><label className="trading-account-check"><input type="checkbox" checked={currentForm.marginControl} onChange={(event) => setFormValue('marginControl', event.target.checked)} /><span>Margin control</span><small>i</small></label><div className="trading-account-field-grid">{modal === 'create' ? <>{(['stocks', 'futures', 'forex', 'crypto', 'others'] as const).map((key) => <label key={key} className="trading-account-field"><span>{key[0].toUpperCase() + key.slice(1)}</span><select value={createDraft.leverage[key]} onChange={(event) => setCreateDraft((current) => ({ ...current, leverage: { ...current.leverage, [key]: event.target.value } }))}>{leverageOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>)}</> : <>{renderLeverageField('Stocks', 'stocks')}{renderLeverageField('Futures', 'futures')}{renderLeverageField('Forex', 'forex')}{renderLeverageField('Crypto', 'crypto')}{renderLeverageField('Others', 'others')}</>}</div></fieldset>
          <fieldset><legend>Commission</legend><label className="trading-account-check"><input type="checkbox" checked={currentForm.futuresOptions} onChange={(event) => setFormValue('futuresOptions', event.target.checked)} /><span>Futures and options</span></label><label className="trading-account-field trading-account-field-wide"><span>Commission per contract</span><input inputMode="decimal" value={currentForm.commissionPerContract} disabled={!currentForm.futuresOptions} onChange={(event) => setFormValue('commissionPerContract', event.target.value)} /></label><label className="trading-account-check"><input type="checkbox" checked={currentForm.othersCommission} onChange={(event) => setFormValue('othersCommission', event.target.checked)} /><span>Others</span></label><div className="trading-account-field-grid"><label className="trading-account-field"><span>Commission</span><input inputMode="decimal" value={currentForm.commission} disabled={!currentForm.othersCommission} onChange={(event) => setFormValue('commission', event.target.value)} /></label><label className="trading-account-field"><span>Commission type</span><select value={currentForm.commissionType} onChange={(event) => setFormValue('commissionType', event.target.value as CommissionType)}><option>Percent</option><option>Fixed</option></select></label></div></fieldset>
        </div>
        <footer><div>{modal === 'settings' ? <><button type="button" className="trading-account-reset" onClick={() => void resetAccount()} disabled={status === 'saving'}>Reset account</button><button type="button" className="trading-account-archive" onClick={() => void archiveAccount()} disabled={status === 'saving' || !activeAccount?.enabled}>Archive</button></> : null}</div><div><button type="button" onClick={() => setModal(null)}>Cancel</button><button type="button" className="trading-account-primary" onClick={() => modal === 'create' ? void createAccount() : saveSettings()} disabled={status === 'saving'}>{modal === 'create' ? 'Create' : 'Save'}</button></div></footer>
      </section></div> : null}
    </section>
  );
}
