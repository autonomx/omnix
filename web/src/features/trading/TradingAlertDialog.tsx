import { useState } from 'react';
import type {
  TradingAlertCondition,
  TradingAlertIndicatorId,
  TradingAlertNotificationChannel,
  TradingAlertTriggerPolicy,
} from './tradingTypes';
import { formatAlertThreshold } from './tradingChartAlerts';
import { MESSAGE_PLACEHOLDERS, type AlertDeliveryEditor } from './alertDelivery';
import { AlertDeliveryFields } from './AlertDeliveryFields';
import { AlertIndicatorPicker } from './AlertIndicatorPicker';
import { resolveIndicatorSelection, type AlertIndicatorChoice, type AlertIndicatorSelection } from './alertIndicatorSources';
import './TradingChartAlertOpaque.css';

export type TradingAlertEditorState = AlertDeliveryEditor & {
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
  trendlinePoints?: Array<{ time: string; price: number }>;
  /** A chart indicator, line and comparison (TVP-1.3), when the alert is on one. */
  indicatorSelection?: AlertIndicatorSelection;
  /** The chart indicator the alert was placed on (its pane), any indicator id. */
  chartIndicatorId?: string;
  // Alerts described by conditions (condition 'conditions') show them read-only until the condition editor ships.
  conditionsSummary?: string;
}

const priceConditionOptions: Array<{ value: TradingAlertCondition; label: string }> = [
  { value: 'price_above', label: 'Price' },
  { value: 'percent_change_above', label: 'Percent change' },
  { value: 'indicator_above', label: 'Indicator' },
  { value: 'volume_above', label: 'Volume' },
];

const trendlineModeOptions: Array<{ value: TradingAlertCondition; label: string }> = [
  { value: 'trendline_crossing', label: 'Crossing' },
  { value: 'trendline_crossing_up', label: 'Crossing Up' },
  { value: 'trendline_crossing_down', label: 'Crossing Down' },
  { value: 'trendline_above', label: 'Greater Than' },
  { value: 'trendline_below', label: 'Less Than' },
];

const triggerOptions: Array<{ value: TradingAlertTriggerPolicy; label: string }> = [
  { value: 'once', label: 'Once only' },
  { value: 'once_per_bar', label: 'Once per bar' },
  { value: 'once_per_bar_close', label: 'Once per bar close' },
  { value: 'once_per_minute', label: 'Once per minute' },
  { value: 'every_time', label: 'Every time' },
];

function conditionFamily(condition: TradingAlertCondition): TradingAlertCondition {
  if (condition.startsWith('trendline_')) return 'trendline_crossing';
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
  indicatorChoices,
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
  /** The chart's indicators (TVP-1.3); without them the dialog offers the legacy indicator list. */
  indicatorChoices?: readonly AlertIndicatorChoice[];
}) {
  // On a chart with indicators, an indicator alert is on one of them (unless editing a legacy alert).
  const usesChartIndicators = Boolean(indicatorChoices?.length) && editor.mode === 'create' && editor.condition.startsWith('indicator_');
  const chartIndicators = indicatorChoices && usesChartIndicators
    ? resolveIndicatorSelection(indicatorChoices, editor.indicatorSelection, editor.chartIndicatorId)
    : undefined;
  const [showConditionNote, setShowConditionNote] = useState(false);
  const family = conditionFamily(editor.condition);
  const direction = conditionDirection(editor.condition);
  const isConditions = editor.condition === 'conditions';
  const isTrendline = editor.condition.startsWith('trendline_');
  const isIndicator = family === 'indicator_above';
  const isPercent = family === 'percent_change_above';

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
          {isConditions ? (
            <div className="trading-alert-value-row"><span>Conditions</span><strong>{editor.conditionsSummary || 'Conditions'}</strong></div>
          ) : (<>
          <div className="trading-alert-condition-row">
            <select
              aria-label="Alert condition"
              value={family}
              onChange={(event) => onChange({ condition: updateCondition(event.target.value as TradingAlertCondition, direction) })}
            >
              {(isTrendline ? [{ value: 'trendline_crossing', label: 'Trendline' }] : priceConditionOptions).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            {usesChartIndicators ? null : (
            <select
              aria-label="Alert crossing"
              value={isTrendline ? editor.condition : direction}
              onChange={(event) => onChange({ condition: isTrendline ? event.target.value as TradingAlertCondition : updateCondition(family, event.target.value as 'above' | 'below') })}
            >
              {isTrendline
                ? trendlineModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)
                : <><option value="above">Crossing above</option><option value="below">Crossing below</option></>}
            </select>
            )}
          </div>
          {isTrendline ? (
            <div className="trading-alert-value-row"><span>Line</span><strong>Selected trendline</strong></div>
          ) : (
            <div className="trading-alert-value-row">
              <span>Value</span>
              <input
                aria-label="Alert value"
                autoFocus
                inputMode="decimal"
                value={editor.threshold}
                placeholder={Number.isFinite(latestPrice) ? String(latestPrice) : 'Value'}
                onChange={(event) => onChange({ threshold: event.target.value })}
                onBlur={(event) => onChange({ threshold: formatAlertThreshold(event.target.value) })}
              />
            </div>
          )}
          {isPercent ? (
            <label className="trading-alert-inline-field">Lookback bars<input inputMode="numeric" value={editor.lookback} onChange={(event) => onChange({ lookback: event.target.value })} /></label>
          ) : null}
          {usesChartIndicators && !indicatorChoices?.some((choice) => !choice.unavailable) ? (
            <small className="trading-alert-condition-note" role="alert">None of this chart&apos;s indicators can be alerted on by the server yet.</small>
          ) : usesChartIndicators ? (
            <AlertIndicatorPicker choices={indicatorChoices ?? []} selection={chartIndicators} onChange={(indicatorSelection) => onChange({ indicatorSelection })} />
          ) : isIndicator ? (
            <div className="trading-alert-condition-row">
              <select aria-label="Alert indicator" value={editor.indicator} onChange={(event) => onChange({ indicator: event.target.value as TradingAlertIndicatorId })}>
                {['sma', 'ema', 'rsi', 'macd', 'bollinger', 'atr', 'vwap', 'stochastic-rsi'].map((item) => <option key={item} value={item}>{item.toUpperCase()}</option>)}
              </select>
              <input aria-label="Alert indicator period" inputMode="numeric" value={editor.period} onChange={(event) => onChange({ period: event.target.value })} />
            </div>
          ) : null}
          </>)}
          <button type="button" className="trading-alert-add-condition" onClick={() => setShowConditionNote((value) => !value)} aria-expanded={showConditionNote}>＋ Add condition</button>
          {showConditionNote ? <small className="trading-alert-condition-note">Server alerts currently evaluate one condition per alert. Use separate alerts for additional conditions.</small> : null}
        </section>

        <dl className="trading-alert-dialog-settings">
          <div>
            <dt>Trigger</dt>
            <dd><select aria-label="Alert trigger" value={editor.triggerPolicy} onChange={(event) => onChange({ triggerPolicy: event.target.value as TradingAlertTriggerPolicy })}>{triggerOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></dd>
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
            <dt>Name</dt>
            <dd><input aria-label="Alert name" value={editor.name ?? ''} placeholder="Optional" maxLength={120} onChange={(event) => onChange({ name: event.target.value })} /></dd>
          </div>
          <div>
            <dt>Message</dt>
            <dd>
              <textarea aria-label="Alert message" rows={2} value={editor.message} placeholder={isTrendline ? `${symbol} crossing trendline` : `${symbol} crossing ${editor.threshold || 'value'}`} maxLength={500} onChange={(event) => onChange({ message: event.target.value })} />
              <small className="trading-alert-placeholders" title="Filled in when the alert triggers; unknown ones stay as written">Placeholders: {MESSAGE_PLACEHOLDERS.join(' ')}</small>
            </dd>
          </div>
          <div>
            <dt>Notifications</dt>
            <dd className="trading-alert-notifications">
              <AlertDeliveryFields editor={editor} onChange={onChange} />
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
