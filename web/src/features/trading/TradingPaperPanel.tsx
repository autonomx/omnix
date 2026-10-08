/* eslint-disable react-hooks/exhaustive-deps -- baseline WP-9.x */
import { useEffect, useMemo, useState } from 'react';
import type { PaperAccount, PaperAccountSnapshot, PaperOrder, PaperOrderType, PaperRiskOrderInput, PaperRiskPreview, PaperSide, PaperTimeInForce } from './paperTypes';
import { localDateTimeToIso, paperOrderTerms, paperOrderTypeLabel, ticketOrderTypes, timeInForceLabels } from './paperOrderTypes';
import { tradingApi, type TradingQuote } from './tradingApi';
import { tradingPaperApi } from './tradingPaperApi';
import { createReplaySnapshot } from './replayTrading';
import { useTradingReplayStore } from './tradingReplayStore';
import { applyPaperTicketPrefill, usePaperTicketPrefill } from './paperTicketRequests';
import { useTradingStore } from './tradingStore';
import './TradingPaper.css';
import { POLL_INTERVALS_MS, startPolling } from '../../shared/timers';

type PaperTicketTab = 'order' | 'dom';
type PaperNotice = { kind: 'success' | 'error'; message: string };
type PaperConfirmation = {
  title: string;
  market: string;
  side: PaperSide;
  quantity: string;
  price: string;
};

function displaySymbol(instrumentId: string): string {
  const raw = instrumentId.split(':').at(-1) ?? instrumentId;
  return raw.replace('-', '/');
}

function displayMarket(instrumentId: string): string {
  const parts = instrumentId.split(':');
  const venue = parts[1] ?? 'Market';
  const rawSymbol = parts.at(-1) ?? instrumentId;
  return `${venue}:${rawSymbol.replaceAll('-', '')}`;
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
    return 'Order not placed: insufficient available paper cash. Check reserved funds or wait for an open order to fill. Reset the account only to clear the simulation.';
  }
  if (raw.includes('insufficient_paper_position')) {
    return 'Order not placed: insufficient paper position to sell.';
  }
  if (raw.includes('paper_account_disabled')) {
    return 'Order not placed: this paper account is archived.';
  }
  if (raw.includes('paper_risk_rejected')) {
    return 'Order not placed: the server risk gate rejected this entry. Review the risk and execution checks below.';
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
  const [riskPct, setRiskPct] = useState('0.35');
  const [riskPreview, setRiskPreview] = useState<PaperRiskPreview | null>(null);
  const [triggerPrice, setTriggerPrice] = useState('');
  const [limitPrice, setLimitPrice] = useState('');
  const [trailValue, setTrailValue] = useState('');
  const [trailUnit, setTrailUnit] = useState<'amount' | 'percent'>('amount');
  const [timeInForce, setTimeInForce] = useState<PaperTimeInForce>('gtc');
  const [expiresAt, setExpiresAt] = useState('');
  const [trailingStopLoss, setTrailingStopLoss] = useState(false);
  const [takeProfitEnabled, setTakeProfitEnabled] = useState(false);
  const [stopLossEnabled, setStopLossEnabled] = useState(false);
  const [takeProfit, setTakeProfit] = useState('');
  const [stopLoss, setStopLoss] = useState('');
  const [quote, setQuote] = useState<TradingQuote | null>(null);
  const [notice, setNotice] = useState<PaperNotice | null>(null);
  const [confirmation, setConfirmation] = useState<PaperConfirmation | null>(null);

  // A long or short position drawing's "Create order" fills the ticket (TVP-3.6); the user still confirms it.
  usePaperTicketPrefill((prefill) => setNotice(applyPaperTicketPrefill(prefill, instrumentId, {
    setTicketTab, setSide, setOrderType, setLimitPrice, setStopLossEnabled, setStopLoss, setTakeProfitEnabled, setTakeProfit, setQuantity,
  }, displaySymbol)));
  const replayMode = useTradingStore((state) => state.replayMode);
  const replaySessionId = useTradingStore((state) => state.replaySessionId);
  const replayBar = useTradingReplayStore((state) => state.bar);
  const replaySnapshot = useTradingReplayStore((state) => state.snapshot);
  const seedReplaySnapshot = useTradingReplayStore((state) => state.seedSnapshot);
  const replayExecutionError = useTradingReplayStore((state) => state.executionError);

  const activeAccount = useMemo(
    () => accounts.find((account) => account.account_id === accountId) ?? accounts[0] ?? null,
    [accountId, accounts],
  );
  const displayedSnapshot = replayMode ? replaySnapshot ?? snapshot : snapshot;
  const symbol = displaySymbol(instrumentId);
  const position = displayedSnapshot?.positions.find((item) => item.instrument_id === instrumentId);
  const replayPrice = replayBar ? parsePositive(replayBar.close) : null;
  const referencePrice = replayMode ? replayPrice : parsePositive(quote?.price ?? '')
    ?? parsePositive(position?.last_price ?? '')
    ?? parsePositive(position?.average_cost ?? '');
  const bidPrice = replayMode ? referencePrice : parsePositive(String(quote?.bid ?? '')) ?? referencePrice;
  const askPrice = replayMode ? referencePrice : parsePositive(String(quote?.ask ?? '')) ?? referencePrice;
  const quotePrice = referencePrice === null ? '—' : number(String(referencePrice), 2);
  const bidLabel = bidPrice === null ? '—' : number(String(bidPrice), 2);
  const askLabel = askPrice === null ? '—' : number(String(askPrice), 2);
  const riskManagedEntry = !replayMode && side === 'buy';
  const orderTypes = ticketOrderTypes({ replay: replayMode, entry: riskManagedEntry });
  // Time in force applies to resting orders; replay has no session clock.
  const timeInForceEnabled = !replayMode && orderType !== 'market';
  const effectiveTimeInForce: PaperTimeInForce = timeInForceEnabled ? timeInForce : 'gtc';
  const usesTriggerPrice = orderType === 'limit' || orderType === 'stop' || orderType === 'stop_limit';
  // A stop already through the market is accepted, as plain stops always
  // were: it triggers on the next price. The ticket says so before placing.
  const stopTrigger = orderType === 'stop' || orderType === 'stop_limit' ? parsePositive(triggerPrice) : null;
  const stopThroughMarket = stopTrigger !== null && (
    side === 'buy'
      ? askPrice !== null && stopTrigger <= askPrice
      : bidPrice !== null && stopTrigger >= bidPrice
  );
  const displayedQuantity = riskManagedEntry ? riskPreview?.recommended_quantity ?? '' : quantity;
  const tradeValue = riskManagedEntry
    ? (riskPreview ? Number(riskPreview.estimated_notional) : null)
    : referencePrice === null ? null : referencePrice * (parsePositive(quantity) ?? 0);
  const balance = displayedSnapshot?.balances.find((item) => item.currency === activeAccount?.base_currency);
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
      const nextSnapshot = nextId ? await tradingPaperApi.snapshot(nextId) : null;
      setSnapshot(nextSnapshot);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    void refresh(preferredAccountId ?? undefined);
  }, [preferredAccountId]);

  useEffect(() => {
    // The replay store owns the replay account and advances it bar by bar;
    // the ticket only seeds it from the live account (once per session).
    if (!replayMode || !snapshot || !activeAccount) return;
    seedReplaySnapshot(createReplaySnapshot(snapshot), `${replaySessionId}:${activeAccount.account_id}:${instrumentId}`);
  }, [activeAccount, instrumentId, replayMode, replaySessionId, seedReplaySnapshot, snapshot]);

  useEffect(() => {
    if (!replayMode || !replayExecutionError) return;
    setStatus('error');
    setNotice({ kind: 'error', message: paperErrorMessage(new Error(replayExecutionError), 'Replay execution') });
  }, [replayExecutionError, replayMode]);

  useEffect(() => {
    if (!accountId) return;
    return startPolling(() => refresh(accountId), POLL_INTERVALS_MS.paperAccount);
  }, [accountId]);

  useEffect(() => {
    if (replayMode) {
      setQuote(null);
      return;
    }
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
  }, [bindingId, instrumentId, replayMode]);

  useEffect(() => {
    if (!orderTypes.includes(orderType)) setOrderType('market');
  }, [orderTypes.join(','), orderType]);

  useEffect(() => {
    if (!riskManagedEntry || !activeAccount || !stopLossEnabled) {
      setRiskPreview(null);
      return;
    }
    // A stop-limit entry is sized at its limit, the most it can pay.
    const entryPrice = orderType === 'market'
      ? askPrice
      : parsePositive(orderType === 'stop_limit' ? limitPrice : triggerPrice);
    const stopPrice = parsePositive(stopLoss);
    const desiredRisk = parsePositive(riskPct);
    if (entryPrice === null || stopPrice === null || desiredRisk === null) {
      setRiskPreview(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void tradingPaperApi.riskPreview(activeAccount.account_id, {
        instrument_id: instrumentId,
        binding_id: bindingId,
        entry_price: String(entryPrice),
        stop_price: String(stopPrice),
        desired_risk_pct: String(desiredRisk),
      }).then((preview) => {
        if (!cancelled) setRiskPreview(preview);
      }).catch(() => {
        if (!cancelled) setRiskPreview(null);
      });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeAccount, askPrice, bindingId, instrumentId, limitPrice, orderType, riskManagedEntry, riskPct, stopLoss, stopLossEnabled, triggerPrice]);

  useEffect(() => {
    if (!notice && !confirmation) return;
    const timer = window.setTimeout(() => {
      setNotice(null);
      setConfirmation(null);
    }, 4_500);
    return () => window.clearTimeout(timer);
  }, [confirmation, notice]);

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
    if (replayMode && !replayBar) {
      setNotice({ kind: 'error', message: 'Select a replay bar before placing an order.' });
      return;
    }
    const numericQuantity = parsePositive(quantity);
    const numericTrigger = parsePositive(triggerPrice);
    const numericTakeProfit = takeProfitEnabled ? parsePositive(takeProfit) : null;
    const numericStopLoss = stopLossEnabled ? parsePositive(stopLoss) : null;
    const numericRiskPct = parsePositive(riskPct);
    const numericLimit = parsePositive(limitPrice);
    const numericTrail = parsePositive(trailValue);
    const expiresIso = effectiveTimeInForce === 'gtd' ? localDateTimeToIso(expiresAt) : null;
    const pricesMissing = (usesTriggerPrice && numericTrigger === null)
      || (orderType === 'stop_limit' && numericLimit === null)
      || (orderType === 'trailing_stop' && (numericTrail === null || (trailUnit === 'percent' && numericTrail >= 100)));
    const expiryMissing = effectiveTimeInForce === 'gtd'
      && (expiresIso === null || new Date(expiresIso).getTime() <= Date.now());
    if (riskManagedEntry) {
      if (
        !stopLossEnabled
        || numericStopLoss === null
        || numericRiskPct === null
        || pricesMissing
        || (takeProfitEnabled && numericTakeProfit === null)
      ) {
        setStatus('error');
        setNotice({ kind: 'error', message: 'New paper entries require a valid stop loss, risk %, order price, and optional take-profit.' });
        return;
      }
      if (expiryMissing) {
        setStatus('error');
        setNotice({ kind: 'error', message: 'Choose a future time for a good-till-date order to expire.' });
        return;
      }
      if (!riskPreview?.allowed) {
        setStatus('error');
        setNotice({ kind: 'error', message: 'Server risk approval is required before submitting this entry.' });
        return;
      }
    } else if (
      numericQuantity === null
      || pricesMissing
      || expiryMissing
      || (takeProfitEnabled && numericTakeProfit === null)
      || (stopLossEnabled && numericStopLoss === null)
    ) {
      setStatus('error');
      setNotice({ kind: 'error', message: 'Enter a valid order quantity, price, trail, expiry, take-profit, and stop-loss value.' });
      return;
    }
    const orderId = `paper-order-${Date.now()}`;
    setStatus('saving');
    setNotice(null);
    setConfirmation(null);
    try {
      let order: PaperOrder;
      let submittedQuantity = quantity;
      if (riskManagedEntry) {
        const result = await tradingPaperApi.placeRiskOrder(activeAccount.account_id, {
          order_id: orderId,
          instrument_id: instrumentId,
          binding_id: bindingId,
          // Entries never offer a trailing stop order (see ticketOrderTypes).
          order_type: orderType as NonNullable<PaperRiskOrderInput['order_type']>,
          trigger_price: orderType === 'market' ? null : triggerPrice,
          limit_price: orderType === 'stop_limit' ? limitPrice : null,
          stop_loss: stopLoss,
          take_profit: takeProfitEnabled ? takeProfit : null,
          trailing_stop_loss: stopLossEnabled && trailingStopLoss,
          desired_risk_pct: riskPct,
          idempotency_key: orderId,
          time_in_force: effectiveTimeInForce,
          expires_at: expiresIso,
        });
        order = result.order;
        submittedQuantity = result.order.quantity;
        setRiskPreview(result.preview);
        await refresh(activeAccount.account_id);
      } else {
        const input = {
          order_id: orderId,
          instrument_id: instrumentId,
          binding_id: bindingId,
          side,
          order_type: orderType,
          quantity,
          limit_price: orderType === 'limit' ? triggerPrice : orderType === 'stop_limit' ? limitPrice : null,
          stop_price: orderType === 'stop' || orderType === 'stop_limit' ? triggerPrice : null,
          trail_amount: orderType === 'trailing_stop' && trailUnit === 'amount' ? trailValue : null,
          trail_percent: orderType === 'trailing_stop' && trailUnit === 'percent' ? trailValue : null,
          reference_price: orderType === 'market'
            ? (side === 'buy' ? askPrice : bidPrice) === null
              ? null
              : String(side === 'buy' ? askPrice : bidPrice)
            : null,
          idempotency_key: orderId,
          time_in_force: effectiveTimeInForce,
          expires_at: expiresIso,
        };
        if (replayMode) {
          if (!replaySnapshot || !replayBar) throw new Error('Replay account is still loading. Select a replay bar and try again.');
          const result = await useTradingReplayStore.getState().placeOrder(input);
          order = result.order;
          setStatus('ready');
        } else {
          order = await tradingPaperApi.placeOrder(activeAccount.account_id, input);
          await refresh(activeAccount.account_id);
        }
      }
      const orderPrice = order.average_fill_price
        ?? order.limit_price
        ?? order.stop_price
        ?? order.reference_price
        ?? (side === 'buy' ? askPrice : bidPrice);
      setConfirmation({
        title: `${paperOrderTypeLabel(orderType)} order ${order.status === 'filled' ? 'executed' : 'submitted'} on`,
        market: displayMarket(instrumentId),
        side,
        quantity: submittedQuantity,
        price: orderPrice === null || orderPrice === undefined ? '—' : number(String(orderPrice), 2),
      });
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
      setNotice({ kind: 'error', message: paperErrorMessage(error) });
    }
  };

  return (
    <section className={`trading-paper-panel${replayMode ? ' is-replay-trading' : ''}`} aria-label="Paper trading order ticket" data-status={status}>
      <header className="trading-paper-header">
        <div className="trading-paper-symbol">
          <span className="trading-paper-symbol-mark" aria-hidden="true">P</span>
          <div>
            <strong>{symbol}</strong>
            <small>{replayMode ? 'Replay simulation' : 'Paper trading'}</small>
          </div>
        </div>
        <div className="trading-paper-header-actions">
          <span className="trading-paper-status">{replayMode ? 'Replay only' : 'Simulation'}</span>
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
            {orderTypes.map((type) => (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={orderType === type}
                onClick={() => setOrderType(type)}
              >
                {type === 'trailing_stop' ? 'Trailing' : paperOrderTypeLabel(type)}
              </button>
            ))}
          </div>

          <label className="trading-paper-units">
            <span>{riskManagedEntry ? 'Units · server sized' : 'Units'}</span>
            <div>
              <input
                aria-label="Order quantity"
                inputMode="decimal"
                value={displayedQuantity}
                readOnly={riskManagedEntry}
                placeholder={riskManagedEntry ? 'Risk preview' : undefined}
                onChange={(event) => setQuantity(event.target.value)}
              />
              <span>{symbol.split('/')[0]}</span>
            </div>
          </label>

          {riskManagedEntry ? (
            <label className="trading-paper-price-field">
              Risk per trade, %
              <input aria-label="Risk per trade percent" inputMode="decimal" value={riskPct} onChange={(event) => setRiskPct(event.target.value)} />
            </label>
          ) : null}

          {usesTriggerPrice ? (
            <label className="trading-paper-price-field">
              {orderType === 'limit' ? 'Limit price' : 'Stop price'}
              <input aria-label={orderType === 'limit' ? 'Limit price' : 'Stop price'} inputMode="decimal" value={triggerPrice} onChange={(event) => setTriggerPrice(event.target.value)} placeholder={quotePrice} />
            </label>
          ) : null}

          {orderType === 'stop_limit' ? (
            <label className="trading-paper-price-field">
              Limit price
              <input aria-label="Limit price" inputMode="decimal" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} placeholder={quotePrice} />
            </label>
          ) : null}

          {orderType === 'trailing_stop' ? (
            <div className="trading-paper-field-pair">
              <label className="trading-paper-price-field">
                {trailUnit === 'percent' ? 'Trail, %' : 'Trail, price'}
                <input aria-label="Trail distance" inputMode="decimal" value={trailValue} onChange={(event) => setTrailValue(event.target.value)} />
              </label>
              <label className="trading-paper-price-field">
                Trail by
                <select aria-label="Trail unit" value={trailUnit} onChange={(event) => setTrailUnit(event.target.value as 'amount' | 'percent')}>
                  <option value="amount">Price</option>
                  <option value="percent">Percent</option>
                </select>
              </label>
            </div>
          ) : null}

          {timeInForceEnabled ? (
            <div className="trading-paper-field-pair">
              <label className="trading-paper-price-field">
                Time in force
                <select aria-label="Time in force" value={timeInForce} onChange={(event) => setTimeInForce(event.target.value as PaperTimeInForce)}>
                  <option value="gtc">{timeInForceLabels.gtc} · until cancelled</option>
                  <option value="day">{timeInForceLabels.day} · session close</option>
                  <option value="gtd">{timeInForceLabels.gtd} · until a date</option>
                </select>
              </label>
              {timeInForce === 'gtd' ? (
                <label className="trading-paper-price-field">
                  Expires
                  <input aria-label="Order expiry" type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
                </label>
              ) : null}
            </div>
          ) : null}

          <dl className="trading-paper-metrics">
            <div><dt>Trade value</dt><dd>{tradeValue === null ? '—' : `${number(String(tradeValue))} ${activeAccount.base_currency}`}</dd></div>
            <div><dt>Available funds</dt><dd>{availableFunds == null ? '—' : `${number(availableFunds)} ${activeAccount.base_currency}`}</dd></div>
            <div><dt>Reserved funds</dt><dd>{reservedFunds == null ? '—' : `${number(reservedFunds)} ${activeAccount.base_currency}`}</dd></div>
            {riskManagedEntry ? <div><dt>Risk at stop</dt><dd>{riskPreview ? `${number(riskPreview.actual_risk_dollars)} ${activeAccount.base_currency} · ${number(riskPreview.actual_risk_pct, 3)}%` : '—'}</dd></div> : null}
            {riskManagedEntry ? <div><dt>Open risk</dt><dd>{riskPreview ? `${number(riskPreview.aggregate_open_risk_dollars)} ${activeAccount.base_currency} · ${number(riskPreview.aggregate_open_risk_pct, 3)}%` : '—'}</dd></div> : null}
            {riskManagedEntry ? <div><dt>Buying power after</dt><dd>{riskPreview ? `${number(riskPreview.buying_power_after)} ${activeAccount.base_currency}` : '—'}</dd></div> : null}
            {riskManagedEntry ? <div><dt>Execution check</dt><dd>{riskPreview ? `${riskPreview.execution_eligible ? 'Eligible' : 'Blocked'} · ${riskPreview.spread_bps == null ? 'spread —' : `${number(riskPreview.spread_bps)} bps`} · ${riskPreview.freshness_mode}` : 'Awaiting server preview'}</dd></div> : null}
          </dl>

          <details className="trading-paper-exits" open>
            <summary><strong>Exits</strong><span aria-hidden="true">⌃</span></summary>
            <div className="trading-paper-exit-row">
              <label><span>Take profit, price</span>{takeProfitEnabled ? <input aria-label="Take profit price" inputMode="decimal" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} placeholder={quotePrice} /> : null}</label>
              <button type="button" role="switch" aria-checked={takeProfitEnabled} aria-label="Enable take profit" className={takeProfitEnabled ? 'active' : undefined} onClick={() => setTakeProfitEnabled((value) => !value)}><i /></button>
            </div>
            <div className="trading-paper-exit-row">
              <label><span>Stop loss, price{riskManagedEntry ? ' · required' : ''}</span>{stopLossEnabled ? <input aria-label="Stop loss price" inputMode="decimal" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)} placeholder={quotePrice} /> : null}</label>
              <button type="button" role="switch" aria-checked={stopLossEnabled} aria-label="Enable stop loss" className={stopLossEnabled ? 'active' : undefined} onClick={() => setStopLossEnabled((value) => !value)}><i /></button>
            </div>
            {riskManagedEntry && stopLossEnabled ? (
              <label className="trading-paper-trailing-toggle">
                <input type="checkbox" aria-label="Trailing stop loss" checked={trailingStopLoss} onChange={(event) => setTrailingStopLoss(event.target.checked)} />
                <span>Trailing · follows the best price by the entry-to-stop distance</span>
              </label>
            ) : null}
          </details>

          {stopThroughMarket ? (
            <div className="trading-paper-notice warning" role="note">
              The stop is already {side === 'buy' ? 'at or below the ask' : 'at or above the bid'}: the order triggers at the next price.
            </div>
          ) : null}

          {riskManagedEntry && riskPreview && !riskPreview.allowed ? (
            <div className="trading-paper-notice error" role="alert">Risk blocked: {riskPreview.reason_codes.join(' · ')}</div>
          ) : null}

          <button type="button" className={`trading-paper-submit ${side}`} disabled={status === 'saving' || (riskManagedEntry && !riskPreview?.allowed)} onClick={() => void placeOrder()}>
            <strong>{side === 'buy' ? 'Buy' : 'Sell'}</strong>
            <span>{displayedQuantity || '0'} {symbol} {paperOrderTypeLabel(orderType).toUpperCase()}</span>
          </button>
          {notice?.kind === 'error' ? <div className="trading-paper-notice error" role="alert" aria-live="polite">{notice.message}</div> : null}
          <small className="trading-paper-disclaimer">Paper only · server-authoritative risk · no live brokerage execution</small>
        </div>
      ) : (
        <div className="trading-paper-create" role="tabpanel" aria-label="Create paper account">
          <strong>Create a paper account</strong>
          <span>Simulate orders on canonical Trading instruments with virtual funds.</span>
          <label>Starting cash<input aria-label="Starting cash" inputMode="decimal" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} /></label>
          <button type="button" onClick={() => void createAccount()} disabled={status === 'saving'}>Create paper account</button>
        </div>
      )}

      {displayedSnapshot ? (
        <div className="trading-paper-activity">
          <details>
            <summary>Positions <span>{displayedSnapshot.positions.filter((positionItem) => Number(positionItem.quantity) !== 0).length}</span></summary>
            <ul className="trading-paper-list">
              {displayedSnapshot.positions.filter((positionItem) => Number(positionItem.quantity) !== 0).map((positionItem) => (
                <li key={positionItem.instrument_id}><strong>{displaySymbol(positionItem.instrument_id)}</strong><span>{positionItem.quantity} @ {positionItem.average_cost}</span></li>
              ))}
              {displayedSnapshot.positions.filter((positionItem) => Number(positionItem.quantity) !== 0).length === 0 ? <li className="empty">No open positions.</li> : null}
            </ul>
          </details>
          <details>
            <summary>Open orders <span>{displayedSnapshot.open_orders.length}</span></summary>
            <ul className="trading-paper-list">
              {displayedSnapshot.open_orders.map((order) => (
                <li key={order.order_id}>
                  <strong>{order.side} {order.quantity} · {paperOrderTypeLabel(order.order_type)}</strong>
                  <span>{displaySymbol(order.instrument_id)} · {paperOrderTerms(order)}</span>
                  <span>{order.order_type === 'trailing_stop' && order.stop_price ? `Stop ${number(order.stop_price)}` : 'Awaiting fill'}</span>
                </li>
              ))}
              {displayedSnapshot.open_orders.length === 0 ? <li className="empty">No open orders.</li> : null}
            </ul>
          </details>
          <details>
            <summary>Account actions</summary>
            <div className="trading-paper-danger-actions">
              <button type="button" disabled={replayMode} onClick={() => void mutate(() => tradingPaperApi.resetAccount(displayedSnapshot.account, initialCash), displayedSnapshot.account.account_id)}>Reset</button>
              <button type="button" disabled={replayMode || !displayedSnapshot.account.enabled} onClick={() => void mutate(() => tradingPaperApi.archiveAccount(displayedSnapshot.account), displayedSnapshot.account.account_id)}>Archive</button>
            </div>
          </details>
        </div>
      ) : null}

      {confirmation ? (
        <div className="trading-paper-confirmation-toast" role="status" aria-live="polite">
          <div className="trading-paper-confirmation-check" aria-hidden="true">✓</div>
          <div className="trading-paper-confirmation-copy">
            <div>{confirmation.title}</div>
            <strong className="trading-paper-confirmation-market"><span aria-hidden="true">≋</span>{confirmation.market}</strong>
            <div className="trading-paper-confirmation-result"><span className={confirmation.side}>{confirmation.side === 'buy' ? 'Buy' : 'Sell'} {confirmation.quantity}</span><span>at <strong>{confirmation.price}</strong></span></div>
          </div>
          <button type="button" className="trading-paper-confirmation-close" aria-label="Dismiss order confirmation" onClick={() => setConfirmation(null)}>×</button>
        </div>
      ) : null}
    </section>
  );
}