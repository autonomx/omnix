import { useEffect, useMemo, useState } from 'react';
import type { PaperAccount, PaperAccountSnapshot, PaperOrderType, PaperSide } from './paperTypes';
import { tradingApi } from './tradingApi';
import { tradingPaperApi } from './tradingPaperApi';
import './TradingPaper.css';

type PaperTicketTab = 'order' | 'dom';
type PaperNotice = { kind: 'success' | 'error'; message: string };

function displaySymbol(instrumentId: string): string {
  const raw = instrumentId.split(':').at(-1) ?? instrumentId;
  return raw.replace('-', '/');
}

function number(value?: string | null, digits = 2): string {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString(undefined, { maximumFractionDigits: digits })
    : '—';
}

function parsePositive(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function paperErrorMessage(error: unknown, action = 'Order'): string {
  const raw = error instanceof Error ? error.message : String(error);
  if (raw.includes('insufficient_paper_cash')) {
    return 'Order not placed: insufficient available paper cash. Check reserved funds, cancel an open order, or reset the account.';
  }
  if (raw.includes('insufficient_paper_position')) {
    return 'Order not placed: insufficient paper position to sell.';
  }
  if (raw.includes('paper_account_disabled')) {
    return 'Order not placed: this paper account is archived.';
  }
  const detail = raw.replace(/^Paper Trading request failed \(\d+\):\s*/, '');
  return `${action} failed: ${detail}`;
}

export function TradingPaperPanel({
  instrumentId,
  bindingId,
  preferredAccountId,
  onAccountChange,
}: {
  instrumentId: string;
  bindingId: string | null;
  preferredAccountId?: string | null;
  onAccountChange?: (accountId: string) => void;
}) {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState(preferredAccountId ?? '');
  const [snapshot, setSnapshot] = useState<PaperAccountSnapshot | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'conflict' | 'error'>('loading');
  const [ticketTab, setTicketTab] = useState<PaperTicketTab>('order');
  const [initialCash, setInitialCash] = useState('100000');
  const [side, setSide] = useState<PaperSide>('buy');
  const [orderType, setOrderType] = useState<PaperOrderType>('market');
  const [quantity, setQuantity] = useState('1');
  const [triggerPrice, setTriggerPrice] = useState('');
  const [takeProfitEnabled, setTakeProfitEnabled] = useState(false);
  const [stopLossEnabled, setStopLossEnabled] = useState(false);
  const [takeProfit, setTakeProfit] = useState('');
  const [stopLoss, setStopLoss] = useState('');
  const [quote, setQuote] = useState<Record<string, string> | null>(null);
  const [notice, setNotice] = useState<PaperNotice | null>(null);

  const activeAccount = useMemo(
    () => accounts.find((account) => account.account_id === accountId) ?? accounts[0] ?? null,
    [accountId, accounts],
  );
  const symbol = displaySymbol(instrumentId);
  const position = snapshot?.positions.find((item) => item.instrument_id === instrumentId);
  const referencePrice = parsePositive(quote?.price ?? '')
    ?? parsePositive(position?.last_price ?? '')
    ?? parsePositive(position?.average_cost ?? '');
  const bidPrice = parsePositive(quote?.bid ?? '') ?? referencePrice;
  const askPrice = parsePositive(quote?.ask ?? '') ?? referencePrice;
  const quotePrice = referencePrice === null ? '—' : number(String(referencePrice), 2);
  const bidLabel = bidPrice === null ? '—' : number(String(bidPrice), 2);
  const askLabel = askPrice === null ? '—' : number(String(askPrice), 2);
  const tradeValue = referencePrice === null ? null : referencePrice * (parsePositive(quantity) ?? 0);
  const balance = snapshot?.balances.find((item) => item.currency === activeAccount?.base_currency);
  const availableFunds = balance?.available;
  const reservedFunds = balance?.reserved;

  const refresh = async (preferredId?: string) => {
    try {
      const nextAccounts = await tradingPaperApi.accounts();
      setAccounts(nextAccounts);
      const retainedId = nextAccounts.some((account) => account.account_id === accountId) ? accountId : '';
      const nextId = preferredId || retainedId || nextAccounts[0]?.account_id || '';
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

  useEffect(() => {
    let cancelled = false;
    setQuote(null);
    void tradingApi.quote(instrumentId, bindingId).then((nextQuote) => {
      if (!cancelled) setQuote(nextQuote);
    }).catch(() => {
      if (!cancelled) setQuote(null);
    });
    return () => {
      cancelled = true;
    };
  }, [bindingId, instrumentId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 4_500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const mutate = async (operation: () => Promise<unknown>, preferredId?: string) => {
    setStatus('saving');
    setNotice(null);
    try {
      await operation();
      await refresh(preferredId);
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
      setNotice({ kind: 'error', message: paperErrorMessage(error, 'Account update') });
    }
  };

  const createAccount = async () => {
    if (parsePositive(initialCash) === null) {
      setStatus('error');
      setNotice({ kind: 'error', message: 'Enter a valid starting cash amount.' });
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
    if (!activeAccount?.enabled) {
      setNotice({ kind: 'error', message: 'Order not placed: select an enabled paper account.' });
      return;
    }
    const numericQuantity = parsePositive(quantity);
    const numericTrigger = parsePositive(triggerPrice);
    if (numericQuantity === null || (orderType !== 'market' && numericTrigger === null)) {
      setStatus('error');
      setNotice({ kind: 'error', message: 'Enter a valid order quantity and price.' });
      return;
    }
    const orderId = `paper-order-${Date.now()}`;
    setStatus('saving');
    setNotice(null);
    try {
      const order = await tradingPaperApi.placeOrder(activeAccount.account_id, {
        order_id: orderId,
        instrument_id: instrumentId,
        binding_id: bindingId,
        side,
        order_type: orderType,
        quantity,
        limit_price: orderType === 'limit' ? triggerPrice : null,
        stop_price: orderType === 'stop' ? triggerPrice : null,
        reference_price: orderType === 'market' && side === 'buy' && askPrice !== null ? String(askPrice) : null,
        idempotency_key: orderId,
      });
      await refresh(activeAccount.account_id);
      setNotice({ kind: 'success', message: `${order.status === 'filled' ? 'Trade filled' : 'Order submitted'} · ${quantity} ${symbol}` });
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
      setNotice({ kind: 'error', message: paperErrorMessage(error) });
    }
  };

  return (
    <section className="trading-paper-panel" aria-label="Paper trading order ticket" data-status={status}>
      <header className="trading-paper-header">
        <div className="trading-paper-symbol">
          <span className="trading-paper-symbol-mark" aria-hidden="true">P</span>
          <div>
            <strong>{symbol}</strong>
            <small>Paper trading</small>
          </div>
        </div>
        <div className="trading-paper-header-actions">
          <span className="trading-paper-status">Simulation</span>
          <button type="button" aria-label="Refresh paper account" onClick={() => void refresh(accountId)}>↻</button>
        </div>
      </header>

      <div className="trading-paper-mode" role="tablist" aria-label="Paper trading ticket mode">
        <button type="button" role="tab" aria-selected={ticketTab === 'order'} onClick={() => setTicketTab('order')}>Order</button>
        <button type="button" role="tab" aria-selected={ticketTab === 'dom'} onClick={() => setTicketTab('dom')}>DOM</button>
      </div>

      <div className="trading-paper-account-row">
        <label>
          Account
          <select
            aria-label="Paper account"
            value={activeAccount?.account_id ?? ''}
            onChange={(event) => {
              setAccountId(event.target.value);
              onAccountChange?.(event.target.value);
              void refresh(event.target.value);
            }}
          >
            <option value="">Select account</option>
            {accounts.map((account) => (
              <option key={account.account_id} value={account.account_id}>
                {account.name}{account.enabled ? '' : ' · archived'}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="trading-paper-new-account" onClick={() => void createAccount()} disabled={status === 'saving'}>
          New account
        </button>
      </div>

      {ticketTab === 'dom' ? (
        <div className="trading-paper-dom" role="tabpanel" aria-label="Depth of market">
          <div className="trading-paper-dom-header"><span>Price</span><span>Size</span></div>
          <div className="trading-paper-dom-empty">
            <strong>Paper DOM</strong>
            <span>Depth data will appear when the selected feed provides a live order book.</span>
          </div>
          <div className="trading-paper-dom-footer">Last reference price <strong>{quotePrice}</strong></div>
        </div>
      ) : activeAccount ? (
        <div className="trading-paper-order" role="tabpanel" aria-label="Paper order entry">
          <div className="trading-paper-quotes" role="group" aria-label="Buy and sell quote actions">
            <button type="button" className={`trading-paper-quote sell${side === 'sell' ? ' active' : ''}`} onClick={() => setSide('sell')}>
              <span>Sell</span><strong>{bidLabel}</strong>
            </button>
            <button type="button" className={`trading-paper-quote buy${side === 'buy' ? ' active' : ''}`} onClick={() => setSide('buy')}>
              <span>Buy</span><strong>{askLabel}</strong>
            </button>
          </div>

          <div className="trading-paper-order-types" role="tablist" aria-label="Paper order type">
            {(['market', 'limit', 'stop'] as PaperOrderType[]).map((type) => (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={orderType === type}
                onClick={() => setOrderType(type)}
              >
                {type[0].toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>

          <label className="trading-paper-units">
            <span>Units</span>
            <div>
              <input aria-label="Order quantity" inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
              <span>{symbol.split('/')[0]}</span>
            </div>
          </label>

          {orderType !== 'market' ? (
            <label className="trading-paper-price-field">
              {orderType === 'limit' ? 'Limit price' : 'Stop price'}
              <input aria-label={orderType === 'limit' ? 'Limit price' : 'Stop price'} inputMode="decimal" value={triggerPrice} onChange={(event) => setTriggerPrice(event.target.value)} placeholder={quotePrice} />
            </label>
          ) : null}

          <dl className="trading-paper-metrics">
            <div><dt>Trade value</dt><dd>{tradeValue === null ? '—' : `${number(String(tradeValue))} ${activeAccount.base_currency}`}</dd></div>
            <div><dt>Available funds</dt><dd>{availableFunds == null ? '—' : `${number(availableFunds)} ${activeAccount.base_currency}`}</dd></div>
            <div><dt>Reserved funds</dt><dd>{reservedFunds == null ? '—' : `${number(reservedFunds)} ${activeAccount.base_currency}`}</dd></div>
          </dl>

          <details className="trading-paper-exits" open>
            <summary><strong>Exits</strong><span aria-hidden="true">⌃</span></summary>
            <div className="trading-paper-exit-row">
              <label><span>Take profit, price</span>{takeProfitEnabled ? <input aria-label="Take profit price" inputMode="decimal" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} placeholder={quotePrice} /> : null}</label>
              <button type="button" role="switch" aria-checked={takeProfitEnabled} aria-label="Enable take profit" className={takeProfitEnabled ? 'active' : undefined} onClick={() => setTakeProfitEnabled((value) => !value)}><i /></button>
            </div>
            <div className="trading-paper-exit-row">
              <label><span>Stop loss, price</span>{stopLossEnabled ? <input aria-label="Stop loss price" inputMode="decimal" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)} placeholder={quotePrice} /> : null}</label>
              <button type="button" role="switch" aria-checked={stopLossEnabled} aria-label="Enable stop loss" className={stopLossEnabled ? 'active' : undefined} onClick={() => setStopLossEnabled((value) => !value)}><i /></button>
            </div>
          </details>

          <button type="button" className={`trading-paper-submit ${side}`} disabled={status === 'saving'} onClick={() => void placeOrder()}>
            <strong>{side === 'buy' ? 'Buy' : 'Sell'}</strong>
            <span>{quantity || '0'} {symbol} {orderType.toUpperCase()}</span>
          </button>
          {notice ? <div className={`trading-paper-notice ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'} aria-live="polite">{notice.message}</div> : null}
          <small className="trading-paper-disclaimer">Paper only · no live brokerage execution</small>
        </div>
      ) : (
        <div className="trading-paper-create" role="tabpanel" aria-label="Create paper account">
          <strong>Create a paper account</strong>
          <span>Simulate orders on canonical Trading instruments with virtual funds.</span>
          <label>Starting cash<input aria-label="Starting cash" inputMode="decimal" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} /></label>
          <button type="button" onClick={() => void createAccount()} disabled={status === 'saving'}>Create paper account</button>
        </div>
      )}

      {snapshot ? (
        <div className="trading-paper-activity">
          <details>
            <summary>Positions <span>{snapshot.positions.filter((positionItem) => Number(positionItem.quantity) !== 0).length}</span></summary>
            <ul className="trading-paper-list">
              {snapshot.positions.filter((positionItem) => Number(positionItem.quantity) !== 0).map((positionItem) => (
                <li key={positionItem.instrument_id}><strong>{displaySymbol(positionItem.instrument_id)}</strong><span>{positionItem.quantity} @ {positionItem.average_cost}</span></li>
              ))}
              {snapshot.positions.filter((positionItem) => Number(positionItem.quantity) !== 0).length === 0 ? <li className="empty">No open positions.</li> : null}
            </ul>
          </details>
          <details>
            <summary>Open orders <span>{snapshot.open_orders.length}</span></summary>
            <ul className="trading-paper-list">
              {snapshot.open_orders.map((order) => (
                <li key={order.order_id}>
                  <strong>{order.side} {order.quantity} · {order.order_type}</strong>
                  <span>{displaySymbol(order.instrument_id)}</span>
                  <button type="button" onClick={() => void mutate(() => tradingPaperApi.cancelOrder(snapshot.account.account_id, order.order_id), snapshot.account.account_id)}>Cancel</button>
                </li>
              ))}
              {snapshot.open_orders.length === 0 ? <li className="empty">No open orders.</li> : null}
            </ul>
          </details>
          <details>
            <summary>Account actions</summary>
            <div className="trading-paper-danger-actions">
              <button type="button" onClick={() => void mutate(() => tradingPaperApi.resetAccount(snapshot.account, initialCash), snapshot.account.account_id)}>Reset</button>
              <button type="button" disabled={!snapshot.account.enabled} onClick={() => void mutate(() => tradingPaperApi.archiveAccount(snapshot.account), snapshot.account.account_id)}>Archive</button>
            </div>
          </details>
        </div>
      ) : null}
    </section>
  );
}
