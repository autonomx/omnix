import { useEffect, useMemo, useState } from 'react';
import { tradingPaperApi } from './tradingPaperApi';
import { tradingStrategyApi } from './tradingStrategyApi';
import type {
  StrategyEvent,
  StrategyMode,
  StrategyProtection,
  TradingStrategyConfig,
} from './tradingStrategyTypes';
import './TradingStrategiesPanel.css';

const defaultStrategy = (accountId: string): TradingStrategyConfig => ({
  strategy_id: `gap-pullback-${Date.now()}`,
  account_id: accountId,
  strategy_kind: 'gap_pullback_v1',
  strategy_version: '1.0.0',
  mode: 'shadow',
  active_universe_id: null,
  enabled: true,
  revision: 1,
  config: {
    strategy_id: 'gap_pullback_v1', strategy_version: '1.0.0',
    minimum_gap_pct: '20', minimum_price: '0.50', maximum_price: '20',
    minimum_premarket_dollar_volume: '1000000', minimum_tod_rvol: '2',
    maximum_spread_bps: '150', opening_impulse_min_pct: '8',
    pullback_min_pct: '3', pullback_max_pct: '35', higher_low_buffer_bps: '20',
    breakout_volume_ratio: '1.25', pivot_left_bars: 2, pivot_right_bars: 2,
    volume_lookback_bars: 10, stop_buffer_bps: '15', reward_multiple: '2',
    entry_start_et: '09:35:00', last_entry_et: '11:30:00',
  },
  risk: {
    risk_per_trade_pct: '0.35', max_daily_loss_pct: '1.5', max_open_risk_pct: '1',
    max_positions: 3, max_trades_per_day: 5, max_trade_value: '25000',
    one_trade_per_symbol_per_day: true, max_spread_bps: '150',
    entry_start_et: '09:35:00', last_entry_et: '11:30:00', force_flat_et: '15:55:00',
    kill_switch: false,
  },
});

function eventTone(event: StrategyEvent): string {
  if (event.event_type === 'rejection' || event.state === 'rejected') return 'rejected';
  if (event.event_type === 'entry_order_submitted' || event.state === 'entry_ready') return 'ready';
  return 'working';
}

export function TradingStrategiesPanel() {
  const [strategies, setStrategies] = useState<TradingStrategyConfig[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState<TradingStrategyConfig | null>(null);
  const [events, setEvents] = useState<StrategyEvent[]>([]);
  const [protections, setProtections] = useState<StrategyProtection[]>([]);
  const [accounts, setAccounts] = useState<Array<{ account_id: string; name: string }>>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');
  const [notice, setNotice] = useState<string | null>(null);

  const selected = useMemo(
    () => strategies.find((item) => item.strategy_id === selectedId) ?? null,
    [selectedId, strategies],
  );

  const refreshDetail = async (strategyId: string) => {
    const [nextEvents, nextProtections] = await Promise.all([
      tradingStrategyApi.events(strategyId),
      tradingStrategyApi.protections(strategyId),
    ]);
    setEvents(nextEvents);
    setProtections(nextProtections);
  };

  const refresh = async () => {
    setStatus('loading');
    try {
      const [nextStrategies, nextAccounts] = await Promise.all([
        tradingStrategyApi.list(),
        tradingPaperApi.accounts(),
      ]);
      setStrategies(nextStrategies);
      setAccounts(nextAccounts.map((item) => ({ account_id: item.account_id, name: item.name })));
      const nextId = nextStrategies.some((item) => item.strategy_id === selectedId)
        ? selectedId
        : nextStrategies[0]?.strategy_id ?? '';
      setSelectedId(nextId);
      const current = nextStrategies.find((item) => item.strategy_id === nextId) ?? null;
      setDraft(current ? structuredClone(current) : null);
      if (nextId) await refreshDetail(nextId);
      else { setEvents([]); setProtections([]); }
      setStatus('ready');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setStatus('error');
    }
  };

  useEffect(() => { void refresh(); }, []);

  useEffect(() => {
    if (!selected) return;
    setDraft(structuredClone(selected));
    void refreshDetail(selected.strategy_id).catch((error) => {
      setNotice(error instanceof Error ? error.message : String(error));
    });
  }, [selected?.strategy_id, selected?.revision]);

  const startNew = () => {
    if (!accounts.length) {
      setNotice('Create a paper account before configuring an automated strategy.');
      return;
    }
    setSelectedId('');
    setEvents([]);
    setProtections([]);
    setDraft(defaultStrategy(accounts[0].account_id));
    setNotice(null);
  };

  const save = async () => {
    if (!draft) return;
    if (!draft.account_id) {
      setNotice('A paper account is required.');
      return;
    }
    if (draft.mode === 'auto_paper' && !draft.active_universe_id) {
      setNotice('AUTO PAPER requires a frozen gapper universe id.');
      return;
    }
    setStatus('saving');
    try {
      const exists = strategies.some((item) => item.strategy_id === draft.strategy_id);
      const saved = exists
        ? await tradingStrategyApi.update(draft)
        : await tradingStrategyApi.create(draft);
      setStrategies((current) => [saved, ...current.filter((item) => item.strategy_id !== saved.strategy_id)]);
      setSelectedId(saved.strategy_id);
      setDraft(structuredClone(saved));
      setNotice(saved.mode === 'auto_paper'
        ? 'AUTO PAPER enabled. Orders remain paper-only and execution data fails closed.'
        : saved.mode === 'shadow'
          ? 'Shadow mode saved. Signals are logged without placing orders.'
          : 'Strategy is off.');
      await refreshDetail(saved.strategy_id);
      setStatus('ready');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setStatus('error');
    }
  };

  const setMode = (mode: StrategyMode) => {
    setDraft((current) => current ? { ...current, mode } : current);
  };

  const latestBySymbol = useMemo(() => {
    const seen = new Set<string>();
    return events.filter((event) => {
      if (seen.has(event.instrument_id)) return false;
      seen.add(event.instrument_id);
      return true;
    }).slice(0, 20);
  }, [events]);

  return (
    <div className="trading-strategies-panel">
      <aside>
        <div className="trading-strategies-heading">
          <div><strong>Strategies</strong><small>Deterministic · paper only</small></div>
          <button type="button" onClick={startNew}>New</button>
        </div>
        {strategies.length ? strategies.map((item) => (
          <button
            key={item.strategy_id}
            type="button"
            className={item.strategy_id === selectedId ? 'active' : undefined}
            onClick={() => setSelectedId(item.strategy_id)}
          >
            <strong>{item.strategy_id}</strong>
            <span>{item.mode.replace('_', ' ')}</span>
          </button>
        )) : <p>No strategies configured.</p>}
      </aside>

      <section>
        {!draft ? (
          <div className="trading-strategies-empty">
            <strong>Configure gap_pullback_v1</strong>
            <p>Create a paper account, freeze a daily candidate universe, then start in shadow mode.</p>
          </div>
        ) : (
          <>
            <header className="trading-strategy-editor-header">
              <div>
                <strong>{draft.strategy_id}</strong>
                <small>gap_pullback_v1 · v{draft.strategy_version} · revision {draft.revision}</small>
              </div>
              <button type="button" onClick={() => void save()} disabled={status === 'saving'}>
                {status === 'saving' ? 'Saving…' : 'Save strategy'}
              </button>
            </header>

            {notice ? <div className="trading-strategy-notice" role="status">{notice}</div> : null}

            <div className="trading-strategy-grid">
              <label>Mode
                <select value={draft.mode} onChange={(event) => setMode(event.target.value as StrategyMode)}>
                  <option value="off">Off</option>
                  <option value="shadow">Shadow</option>
                  <option value="auto_paper">Auto paper</option>
                </select>
              </label>
              <label>Paper account
                <select value={draft.account_id} onChange={(event) => setDraft({ ...draft, account_id: event.target.value })}>
                  {accounts.map((account) => <option key={account.account_id} value={account.account_id}>{account.name}</option>)}
                </select>
              </label>
              <label>Frozen universe id
                <input value={draft.active_universe_id ?? ''} onChange={(event) => setDraft({ ...draft, active_universe_id: event.target.value || null })} placeholder="gappers-2026-08-18" />
              </label>
              <label>Risk / trade (%)
                <input type="number" step="0.05" min="0.01" max="5" value={String(draft.risk.risk_per_trade_pct)} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, risk_per_trade_pct: event.target.value } })} />
              </label>
              <label>Max daily loss (%)
                <input type="number" step="0.1" min="0.1" max="20" value={String(draft.risk.max_daily_loss_pct)} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, max_daily_loss_pct: event.target.value } })} />
              </label>
              <label>Max positions
                <input type="number" min="1" max="50" value={draft.risk.max_positions} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, max_positions: Number(event.target.value) } })} />
              </label>
              <label>Max spread (bps)
                <input type="number" min="1" value={String(draft.risk.max_spread_bps)} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, max_spread_bps: event.target.value } })} />
              </label>
              <label>Kill switch
                <input type="checkbox" checked={draft.risk.kill_switch} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, kill_switch: event.target.checked } })} />
              </label>
            </div>

            <div className="trading-strategy-safety">
              <strong>Execution gates</strong>
              <span>Execution-grade quote required</span><span>Stale data → no fill</span>
              <span>One trade / symbol / day</span><span>Server-side stop + target protection</span>
              <span>AI and model scores are shadow-only</span><span>No live broker route</span>
            </div>

            <div className="trading-strategy-monitoring">
              <section>
                <header><strong>Candidate state</strong><span>{latestBySymbol.length}</span></header>
                <div className="trading-strategy-table">
                  {latestBySymbol.map((event) => (
                    <div key={event.event_id} data-tone={eventTone(event)}>
                      <strong>{event.instrument_id.split(':').at(-1)}</strong>
                      <span>{event.state.replaceAll('_', ' ')}</span>
                      <small>{event.reason_code?.replaceAll('_', ' ') ?? event.event_type}</small>
                    </div>
                  ))}
                  {!latestBySymbol.length ? <p>No evaluated candidates yet.</p> : null}
                </div>
              </section>
              <section>
                <header><strong>Server protection</strong><span>{protections.length}</span></header>
                <div className="trading-strategy-table">
                  {protections.map((item) => (
                    <div key={item.protection_id} data-tone={item.status === 'active' ? 'ready' : 'working'}>
                      <strong>{item.instrument_id.split(':').at(-1)}</strong>
                      <span>{item.status.replaceAll('_', ' ')}</span>
                      <small>Stop {String(item.stop_price)} · Target {String(item.target_price)}</small>
                    </div>
                  ))}
                  {!protections.length ? <p>No active protections.</p> : null}
                </div>
              </section>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
