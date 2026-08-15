import { useState } from 'react';
import type {
  TradingAlertCondition,
  TradingAlertIndicatorId,
  TradingAlertNotificationChannel,
  TradingAlertTriggerPolicy,
} from './tradingTypes';

export type TradingAlertEditorState = {
  mode: 'create' | 'edit';
  alertId: string | null;
  x: number;
  y: number;
  condition: TradingAlertCondition;
  threshold: string;
  expiresAt: string;
  expiration: 'never' | '1h' | '1d' | '1w';
  triggerPolicy: TradingAlertTriggerPolicy;
  message: string;
  notifications: TradingAlertNotificationChannel[];
  indicator: TradingAlertIndicatorId;
  period: string;
  lookback: string;
}

const conditionOptions: Array<{ value: TradingAlertCondition; label: string }> = [
  { value: 'price_above', label: 'Price' },
  { value: 'percent_change_above', label: 'Percent change' },
  { value: 'indicator_above', label: 'Indicator' },
  { value: 'volume_above', label: 'Volume' },
];

const notificationOptions: Array<{ value: TradingAlertNotificationChannel; label: string }> = [
  { value: 'app', label: 'App' },
  { value: 'toast', label: 'Toasts' },
  { value: 'sound', label: 'Sound' },
];

function conditionFamily(condition: TradingAlertCondition): TradingAlertCondition {
  if (condition.startsWith('percent_change_')) return 'percent_change_above';
  if (condition.startsWith('indicator_')) return 'indicator_above';
  if (condition.startsWith('volume_')) return 'volume_above';
  return 'price_above';
}

function conditionDirection(condition: TradingAlertCondition): 'above' | 'below' {
  return condition.endsWith('_below') ? 'below' : 'above';
}

function updateCondition(
  family: TradingAlertCondition,
  direction: 'above' | 'below',
): TradingAlertCondition {
  const prefix = family.replace(/_above$/, '');
  return `${prefix}_${direction}` as TradingAlertCondition;
}

function expirationLabel(value: TradingAlertEditorState['expiration']): string {
  if (value === '1h') return '1 hour';
  if (value === '1d') return '1 day';
  if (value === '1w') return '1 week';
  return 'Never';
}

export function TradingAlertDialog({
  editor,
  symbol,
  latestPrice,
  status,
  onChange,
  onSubmit,
  onClose,
  onToggle,
  onArchive,
}: {
  editor: TradingAlertEditorState;
  symbol: string;
  latestPrice: number;
  status: string;
  onChange: (patch: Partial<TradingAlertEditorState>) => void;
  onSubmit: () => void;
  onClose: () => void;
  onToggle?: () => void;
  onArchive?: () => void;
}) {
  const [showConditionNote, setShowConditionNote] = useState(false);
  const family = conditionFamily(editor.condition);
  const direction = conditionDirection(editor.condition);
  const isIndicator = family === 'indicator_above';
  const isPercent = family === 'percent_change_above';

  const toggleNotification = (channel: TradingAlertNotificationChannel) => {
    const next = editor.notifications.includes(channel)
      ? editor.notifications.filter((item) => item !== channel)
      : [...editor.notifications, channel];
    onChange({ notifications: next });
  };

  return (
    <form
      className="trading-chart-alert-editor"
      role="dialog"
      aria-modal="false"
      aria-label={`${editor.mode === 'create' ? 'Create' : 'Edit'} alert on ${symbol}`}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <header>
        <div className="trading-alert-dialog-title">
          <strong>{editor.mode === 'create' ? 'Create alert on' : 'Edit alert on'}</strong>
          <span className="trading-alert-dialog-symbol"><i aria-hidden="true">◈</i>{symbol}<span aria-hidden="true">⌄</span></span>
        </div>
        <button type="button" onClick={onClose} aria-label="Close alert editor">×</button>
      </header>

      <div className="trading-alert-dialog-body">
        <section className="trading-alert-condition-section" aria-label="Alert condition">
          <div className="trading-alert-section-heading"><strong>Condition</strong><span>Price, indicator, or volume</span></div>
          <div className="trading-alert-condition-row">
            <select
              aria-label="Alert condition"
              value={family}
              onChange={(event) => onChange({ condition: updateCondition(event.target.value as TradingAlertCondition, direction) })}
            >
              {conditionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select
              aria-label="Alert crossing"
              value={direction}
              onChange={(event) => onChange({ condition: updateCondition(family, event.target.value as 'above' | 'below') })}
            >
              <option value="above">Crossing above</option>
              <option value="below">Crossing below</option>
            </select>
          </div>
          <div className="trading-alert-value-row">
            <span>Value</span>
            <input
              aria-label="Alert value"
              autoFocus
              inputMode="decimal"
              value={editor.threshold}
              placeholder={Number.isFinite(latestPrice) ? String(latestPrice) : 'Value'}
              onChange={(event) => onChange({ threshold: event.target.value })}
            />
          </div>
          {isPercent ? (
            <label className="trading-alert-inline-field">Lookback bars<input inputMode="numeric" value={editor.lookback} onChange={(event) => onChange({ lookback: event.target.value })} /></label>
          ) : null}
          {isIndicator ? (
            <div className="trading-alert-condition-row">
              <select aria-label="Alert indicator" value={editor.indicator} onChange={(event) => onChange({ indicator: event.target.value as TradingAlertIndicatorId })}>
                {['sma', 'ema', 'rsi', 'macd', 'bollinger', 'atr', 'vwap'].map((item) => <option key={item}>{item.toUpperCase()}</option>)}
              </select>
              <input aria-label="Alert indicator period" inputMode="numeric" value={editor.period} onChange={(event) => onChange({ period: event.target.value })} />
            </div>
          ) : null}
          <button type="button" className="trading-alert-add-condition" onClick={() => setShowConditionNote((value) => !value)} aria-expanded={showConditionNote}>＋ Add condition</button>
          {showConditionNote ? <small className="trading-alert-condition-note">Server alerts currently evaluate one condition per alert. Use separate alerts for additional conditions.</small> : null}
        </section>

        <dl className="trading-alert-dialog-settings">
          <div>
            <dt>Trigger</dt>
            <dd><select aria-label="Alert trigger" value={editor.triggerPolicy} onChange={(event) => onChange({ triggerPolicy: event.target.value as TradingAlertTriggerPolicy })}><option value="once">Once only</option><option value="once_per_bar">Once per bar</option><option value="every_time">Every time</option></select></dd>
          </div>
          <div>
            <dt>Expiration</dt>
            <dd>
              <select aria-label="Alert expiration" value={editor.expiration} onChange={(event) => onChange({ expiration: event.target.value as TradingAlertEditorState['expiration'] })}>
                {(['never', '1h', '1d', '1w'] as const).map((item) => <option key={item} value={item}>{expirationLabel(item)}</option>)}
              </select>
              {editor.expiration !== 'never' ? <input aria-label="Alert expiration date" type="datetime-local" value={editor.expiresAt} onChange={(event) => onChange({ expiresAt: event.target.value })} /> : null}
            </dd>
          </div>
          <div>
            <dt>Message</dt>
            <dd><input aria-label="Alert message" value={editor.message} placeholder={`${symbol} crossing ${editor.threshold || 'value'}`} maxLength={500} onChange={(event) => onChange({ message: event.target.value })} /></dd>
          </div>
          <div>
            <dt>Notifications</dt>
            <dd className="trading-alert-notifications">
              {notificationOptions.map((option) => <label key={option.value}><input type="checkbox" checked={editor.notifications.includes(option.value)} onChange={() => toggleNotification(option.value)} />{option.label}</label>)}
            </dd>
          </div>
        </dl>
      </div>

      <footer className="trading-chart-alert-editor-actions">
        <small className="trading-chart-alert-editor-status">Server state: {status}</small>
        <button type="button" onClick={onClose}>Cancel</button>
        {onToggle ? <button type="button" onClick={onToggle}>{editor.mode === 'edit' ? 'Disable / enable' : 'Test'}</button> : null}
        {onArchive ? <button type="button" className="danger" onClick={onArchive}>Delete</button> : null}
        <button type="submit" disabled={status === 'saving'}>{editor.mode === 'create' ? 'Create alert' : 'Save changes'}</button>
      </footer>
    </form>
  );
}
