import { useEffect, useMemo, useState } from 'react';
import { TradingAlertDialog, type TradingAlertEditorState } from './TradingAlertDialog';
import {
  alertVisualState,
  chartAlertCreateInput,
  chartAlertUpdateInput,
  expirationTimestamp,
  notifyTradingAlertsChanged,
} from './tradingChartAlerts';
import { tradingApi } from './tradingApi';
import type {
  TradingAlert,
  TradingAlertCondition,
  TradingAlertTrigger,
} from './tradingTypes';
import './TradingChartAlertOverlay.css';
import './TradingAlertsPanel.css';

type AlertsTab = 'alerts' | 'log';

const conditions: Array<{ value: TradingAlertCondition; label: string }> = [
  { value: 'price_above', label: 'Price crosses above' },
  { value: 'price_below', label: 'Price crosses below' },
  { value: 'percent_change_above', label: 'Percent change crosses above' },
  { value: 'percent_change_below', label: 'Percent change crosses below' },
  { value: 'indicator_above', label: 'Indicator threshold above' },
  { value: 'indicator_below', label: 'Indicator threshold below' },
  { value: 'indicator_cross_above', label: 'Indicator crosses above' },
  { value: 'indicator_cross_below', label: 'Indicator crosses below' },
  { value: 'volume_above', label: 'Volume crosses above' },
  { value: 'volume_below', label: 'Volume crosses below' },
];

const indicatorLabels: Record<string, string> = {
  atr: 'ATR',
  bollinger: 'Bollinger Bands',
  ema: 'EMA',
  macd: 'MACD',
  rsi: 'RSI',
  sma: 'SMA',
  vwap: 'VWAP',
};

function symbolForInstrumentId(instrumentId: string): string {
  const symbol = instrumentId.split(':').at(-1) ?? instrumentId;
  return symbol.replace(/[-_/]/g, '').toUpperCase();
}

function localDateTime(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function isoDateTime(value: string): string | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null;
}

function conditionLabel(condition: TradingAlertCondition): string {
  return conditions.find((item) => item.value === condition)?.label ?? condition;
}

function directionLabel(condition: TradingAlertCondition): string {
  return condition.endsWith('_below') ? 'Crossing Down' : 'Crossing Up';
}

function alertTitle(alert: TradingAlert): string {
  const message = alert.parameters.message?.trim();
  if (message) return message;

  const symbol = symbolForInstrumentId(alert.instrument_id);
  const indicatorId = alert.parameters.indicator_id;
  if (indicatorId) {
    const indicator = indicatorLabels[indicatorId] ?? indicatorId.toUpperCase();
    const period = alert.parameters.period ?? 14;
    return `${indicator} (${period}) ${directionLabel(alert.condition_type)} ${alert.threshold}`;
  }
  if (alert.condition_type.startsWith('price_')) {
    return `${symbol} ${directionLabel(alert.condition_type)} ${alert.threshold}`;
  }
  return `${symbol} ${conditionLabel(alert.condition_type)} ${alert.threshold}`;
}

function alertStatus(alert: TradingAlert): { label: string; className: string } {
  if (alertVisualState(alert) === 'expired') return { label: 'Stopped - Expired', className: 'expired' };
  if (!alert.enabled && alert.last_triggered_at) return { label: 'Stopped - Triggered', className: 'triggered' };
  if (!alert.enabled) return { label: 'Stopped', className: 'stopped' };
  return { label: 'Active', className: 'active' };
}

function formatGroupDate(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat(undefined, { month: 'long', day: 'numeric' }).format(date).toUpperCase()
    : 'RECENT';
}

function formatLogTime(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date)
    : 'Unknown time';
}

function editorDefaults(): TradingAlertEditorState {
  return {
    mode: 'create',
    alertId: null,
    x: 0,
    y: 0,
    condition: 'price_above',
    threshold: '',
    expiresAt: '',
    expiration: 'never',
    triggerPolicy: 'every_time',
    message: '',
    notifications: ['app', 'toast'],
    indicator: 'rsi',
    period: '14',
    lookback: '1',
  };
}

function editorForAlert(alert: TradingAlert): TradingAlertEditorState {
  return {
    mode: 'edit',
    alertId: alert.alert_id,
    x: 0,
    y: 0,
    condition: alert.condition_type,
    threshold: alert.threshold,
    expiresAt: localDateTime(alert.expires_at),
    expiration: alert.expires_at ? '1d' : 'never',
    triggerPolicy: alert.parameters.trigger_policy
      ?? (alert.cooldown_seconds > 0 ? 'once_per_bar' : 'every_time'),
    message: alert.parameters.message ?? '',
    notifications: alert.parameters.notification_channels ?? ['app', 'toast'],
    indicator: alert.parameters.indicator_id ?? 'rsi',
    period: String(alert.parameters.period ?? 14),
    lookback: String(alert.parameters.lookback_bars ?? 1),
  };
}

export function TradingAlertsPanel({
  instrumentId,
  bindingId,
  interval = '1m',
}: {
  instrumentId: string;
  bindingId: string | null;
  interval?: string;
}) {
  const [tab, setTab] = useState<AlertsTab>('alerts');
  const [alerts, setAlerts] = useState<TradingAlert[]>([]);
  const [triggers, setTriggers] = useState<TradingAlertTrigger[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'conflict' | 'error'>('loading');
  const [editor, setEditor] = useState<TradingAlertEditorState | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [sortBySymbol, setSortBySymbol] = useState(false);
  const [listMenuOpen, setListMenuOpen] = useState(false);
  const [rowMenuId, setRowMenuId] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [nextAlerts, nextTriggers] = await Promise.all([
        tradingApi.alerts(),
        tradingApi.alertTriggers(),
      ]);
      setAlerts(nextAlerts);
      setTriggers(nextTriggers);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    void refresh();
    const changed = () => void refresh();
    window.addEventListener('omnix:trading-alerts-changed', changed);
    return () => window.removeEventListener('omnix:trading-alerts-changed', changed);
  }, []);

  const runMutation = async (mutation: () => Promise<unknown>) => {
    setStatus('saving');
    try {
      await mutation();
      notifyTradingAlertsChanged();
      await refresh();
      setEditor(null);
      setRowMenuId(null);
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
    }
  };

  const alertById = useMemo(() => new Map(alerts.map((alert) => [alert.alert_id, alert])), [alerts]);
  const query = search.trim().toLowerCase();
  const visibleAlerts = useMemo(() => {
    const filtered = alerts.filter((alert) => {
      if (!query) return true;
      const symbol = symbolForInstrumentId(alert.instrument_id).toLowerCase();
      return `${symbol} ${alertTitle(alert)} ${alert.parameters.message ?? ''}`.toLowerCase().includes(query);
    });
    return filtered.sort((left, right) => {
      if (sortBySymbol) return symbolForInstrumentId(left.instrument_id).localeCompare(symbolForInstrumentId(right.instrument_id));
      return (right.last_triggered_at ?? '').localeCompare(left.last_triggered_at ?? '');
    });
  }, [alerts, query, sortBySymbol]);

  const groupedLogs = useMemo(() => {
    const groups = new Map<string, TradingAlertTrigger[]>();
    triggers
      .filter((trigger) => {
        if (!query) return true;
        const alert = alertById.get(trigger.alert_id);
        const symbol = symbolForInstrumentId(trigger.instrument_id);
        return `${symbol} ${alert ? alertTitle(alert) : conditionLabel(trigger.condition_type)}`.toLowerCase().includes(query);
      })
      .sort((left, right) => right.observed_at.localeCompare(left.observed_at))
      .forEach((trigger) => {
        const key = formatGroupDate(trigger.observed_at);
        groups.set(key, [...(groups.get(key) ?? []), trigger]);
      });
    return [...groups.entries()].map(([label, items]) => ({ label, items }));
  }, [alertById, query, triggers]);

  const openCreate = () => {
    setRowMenuId(null);
    setListMenuOpen(false);
    setEditor(editorDefaults());
  };

  const openEdit = (alert: TradingAlert) => {
    setRowMenuId(null);
    setEditor(editorForAlert(alert));
  };

  const saveEditor = async () => {
    if (!editor || editor.mode !== 'edit') return;
    const threshold = Number(editor.threshold);
    const alert = alerts.find((item) => item.alert_id === editor.alertId);
    if (!alert || !Number.isFinite(threshold)) {
      setStatus('error');
      return;
    }
    await runMutation(() => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, {
      threshold: String(threshold),
      condition_type: editor.condition,
      expires_at: editor.expiresAt ? isoDateTime(editor.expiresAt) : expirationTimestamp(editor.expiration),
      trigger_policy: editor.triggerPolicy,
      message: editor.message,
      notification_channels: editor.notifications,
    })));
  };

  const createAlert = async () => {
    if (!editor || editor.mode !== 'create') return;
    const threshold = Number(editor.threshold);
    if (!Number.isFinite(threshold)) {
      setStatus('error');
      return;
    }
    const input = chartAlertCreateInput({
      alertId: `panel-alert-${crypto.randomUUID()}`,
      instrumentId,
      bindingId,
      interval,
      threshold,
      latestPrice: Number.NaN,
      condition: editor.condition === 'price_above' || editor.condition === 'price_below' ? editor.condition : undefined,
      expiration: editor.expiration,
      triggerPolicy: editor.triggerPolicy,
      message: editor.message,
      notificationChannels: editor.notifications,
    });
    input.condition_type = editor.condition;
    input.parameters = {
      ...input.parameters,
      indicator_id: editor.condition.startsWith('indicator_') ? editor.indicator : null,
      period: Number(editor.period) || 14,
      lookback_bars: Number(editor.lookback) || 1,
    };
    input.expires_at = editor.expiresAt ? isoDateTime(editor.expiresAt) : input.expires_at;
    await runMutation(() => tradingApi.createAlert(input));
  };

  const activeAlert = alerts.find((alert) => alert.instrument_id === instrumentId);
  const dialogAlert = editor?.mode === 'edit' ? alerts.find((alert) => alert.alert_id === editor.alertId) : null;
  const dialogSymbol = symbolForInstrumentId(dialogAlert?.instrument_id ?? instrumentId);
  const dialogLatestPrice = Number(activeAlert?.last_observed_value ?? Number.NaN);

  return (
    <section className="trading-alerts-panel" aria-label="Server-side Trading alerts" data-status={status}>
      <header className="trading-alerts-panel-header">
        <nav role="tablist" aria-label="Trading alerts sections">
          <button type="button" role="tab" aria-selected={tab === 'alerts'} aria-controls="trading-alerts-list" onClick={() => setTab('alerts')}>Alerts</button>
          <button type="button" role="tab" aria-selected={tab === 'log'} aria-controls="trading-alerts-log" onClick={() => setTab('log')}>Log <span className="trading-alert-log-count">{triggers.length}</span></button>
        </nav>
      </header>

      {tab === 'alerts' ? (
        <section id="trading-alerts-list" role="tabpanel" aria-label="Alert list" className="trading-alerts-list-panel">
          <div className="trading-alerts-toolbar">
            <button type="button" className="trading-alert-icon-button trading-alert-add-button" aria-label="Add alert" title="Add alert" onClick={openCreate}>+</button>
            <button type="button" className="trading-alert-icon-button" aria-label="Search alerts" aria-pressed={searchOpen} title="Search alerts" onClick={() => setSearchOpen((value) => !value)}>⌕</button>
            <button type="button" className="trading-alert-icon-button" aria-label="Sort alerts" title={sortBySymbol ? 'Sort by recent activity' : 'Sort by symbol'} onClick={() => setSortBySymbol((value) => !value)}>↕</button>
            <div className="trading-alert-list-options">
              <button type="button" className="trading-alert-icon-button" aria-label="Alert list options" aria-expanded={listMenuOpen} title="Alert list options" onClick={() => setListMenuOpen((value) => !value)}>•••</button>
              {listMenuOpen ? (
                <div className="trading-alert-options-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => { setListMenuOpen(false); void refresh(); }}>Refresh alerts</button>
                  <button type="button" role="menuitem" onClick={() => { setListMenuOpen(false); setSearch(''); setSearchOpen(false); }}>Clear search</button>
                </div>
              ) : null}
            </div>
          </div>
          {searchOpen ? <input className="trading-alert-search" aria-label="Search alerts" placeholder="Search alerts" value={search} onChange={(event) => setSearch(event.target.value)} /> : null}
          {visibleAlerts.length > 0 ? (
            <ul className="trading-alert-list">
              {visibleAlerts.map((alert) => {
                const symbol = symbolForInstrumentId(alert.instrument_id);
                const title = alertTitle(alert);
                const state = alertStatus(alert);
                return (
                  <li key={alert.alert_id} data-alert-state={alertVisualState(alert)} className={alert.instrument_id === instrumentId ? 'current' : undefined}>
                    <button type="button" className="trading-alert-row-main" onClick={() => openEdit(alert)} aria-label={`Edit ${title}`}>
                      <span className="trading-alert-symbol-badge" aria-hidden="true">{symbol.slice(0, 1)}</span>
                      <span className="trading-alert-row-copy">
                        <span className="trading-alert-row-heading"><b className="trading-alert-row-symbol" title={`Symbol ${symbol}`}>{symbol}</b><strong title={title}>{title}</strong></span>
                        <span>{alert.evaluation_policy.interval} <i>•</i> <em className={`state-${state.className}`}>{state.label}</em> <i>•</i> <small title="Alert trigger">⌁</small></span>
                      </span>
                    </button>
                    <div className="trading-alert-row-options">
                      <button type="button" className="trading-alert-row-options-button" aria-label={`Options for ${title}`} aria-expanded={rowMenuId === alert.alert_id} onClick={() => setRowMenuId((value) => value === alert.alert_id ? null : alert.alert_id)}>•••</button>
                      {rowMenuId === alert.alert_id ? (
                        <div className="trading-alert-options-menu" role="menu">
                          <button type="button" role="menuitem" onClick={() => openEdit(alert)}>Edit alert</button>
                          <button type="button" role="menuitem" onClick={() => void runMutation(() => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, { enabled: !alert.enabled })))}>{alert.enabled ? 'Disable alert' : 'Enable alert'}</button>
                          <button type="button" role="menuitem" onClick={() => void runMutation(() => tradingApi.archiveAlert(alert))}>Delete alert</button>
                        </div>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="trading-alerts-empty"><strong>No alerts</strong><span>Create an alert with + to monitor this workspace.</span></div>
          )}
        </section>
      ) : (
        <section id="trading-alerts-log" role="tabpanel" aria-label="Alert log" className="trading-alert-log-panel">
          <div className="trading-alerts-toolbar trading-alert-log-toolbar">
            <button type="button" className="trading-alert-icon-button" aria-label="Refresh log" title="Refresh log" onClick={() => void refresh()}>↻</button>
            <div className="trading-alert-list-options">
              <button type="button" className="trading-alert-icon-button" aria-label="Log options" title="Log options" onClick={() => void refresh()}>•••</button>
            </div>
          </div>
          {groupedLogs.length > 0 ? groupedLogs.map((group) => (
            <section key={group.label} className="trading-alert-log-group" aria-label={group.label}>
              <h3>{group.label}</h3>
              <ul>
                {group.items.map((trigger) => {
                  const alert = alertById.get(trigger.alert_id);
                  const symbol = symbolForInstrumentId(trigger.instrument_id);
                  const title = alert ? alertTitle(alert) : `${symbol} ${conditionLabel(trigger.condition_type)} ${trigger.threshold}`;
                  return (
                    <li key={trigger.trigger_id}>
                      <span className="trading-alert-symbol-badge" aria-hidden="true">{symbol.slice(0, 1)}</span>
                      <span className="trading-alert-row-copy"><strong title={title}>{title}</strong><span><b>{symbol}</b>, {alert?.evaluation_policy.interval ?? '-'} <i>•</i> {formatLogTime(trigger.observed_at)}</span></span>
                    </li>
                  );
                })}
              </ul>
            </section>
          )) : <div className="trading-alerts-empty"><strong>No log entries</strong><span>Triggered alerts will appear here.</span></div>}
        </section>
      )}

      {editor ? (
        <div className="trading-alert-panel-editor">
          <TradingAlertDialog
            editor={editor}
            symbol={dialogSymbol}
            latestPrice={dialogLatestPrice}
            status={status}
            onChange={(patch) => setEditor((current) => current ? { ...current, ...patch } : current)}
            onSubmit={() => void (editor.mode === 'create' ? createAlert() : saveEditor())}
            onClose={() => setEditor(null)}
            onToggle={editor.mode === 'edit' && dialogAlert ? () => void runMutation(() => tradingApi.updateAlert(dialogAlert, chartAlertUpdateInput(dialogAlert, { enabled: !dialogAlert.enabled }))) : undefined}
            onArchive={editor.mode === 'edit' && dialogAlert ? () => void runMutation(() => tradingApi.archiveAlert(dialogAlert)) : undefined}
          />
        </div>
      ) : null}
    </section>
  );
}
