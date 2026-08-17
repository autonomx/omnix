import { useMemo, useState } from 'react';
import {
  indicatorPlotDefinitions,
  indicatorDefaultBackgroundColor,
  indicatorUsesSeparatePane,
  type CoreIndicatorId,
  type CoreIndicatorInstance,
  type IndicatorLineStyle,
  type CoreIndicatorStyle,
} from './indicators/coreIndicators';
import './TradingIndicatorSettings.css';

type SettingsTab = 'inputs' | 'style' | 'visibility';

const displayNames: Partial<Record<CoreIndicatorId, string>> = {
  atr: 'Average True Range',
  bollinger: 'Bollinger Bands',
  'bull-market-band': 'Bull Market Support Band',
  'death-cross': 'Death Cross',
  ema: 'Exponential Moving Average',
  'ema-stack': 'EMA Stack',
  'fair-value-gap': 'Fair Value Gap',
  'golden-cross': 'Golden Cross',
  'ideal-bb': 'IDEAL BB with MA',
  'log-macd': 'Log MACD',
  'macd-dema': 'MACD DEMA',
  macd: 'Moving Average Convergence Divergence',
  rsi: 'Relative Strength Index',
  'rsi-divergence': 'RSI Divergence',
  sma: 'Simple Moving Average',
  'stochastic-rsi': 'Stochastic RSI',
  'swing-liquidity': 'Swing Levels and Liquidity',
  'volume-profile': 'Volume Profile',
  vwap: 'Volume Weighted Average Price',
};

const plotColors = ['#ffd43b', '#e599f7', '#74c0fc', '#ff922b', '#20c997', '#ff6b6b'];
const lineStyleOptions: Array<{ value: IndicatorLineStyle; label: string }> = [
  { value: 'solid', label: '────' },
  { value: 'dotted', label: '····' },
  { value: 'dashed', label: '– – –' },
  { value: 'large-dashed', label: '—  —' },
  { value: 'sparse-dotted', label: '·  ·' },
];

function supportsBackground(id: CoreIndicatorId, plotCount: number): boolean {
  return plotCount >= 2 && !indicatorUsesSeparatePane(id);
}

function titleFor(indicator: CoreIndicatorInstance): string {
  return displayNames[indicator.id] ?? indicator.id.toUpperCase();
}

function defaultPlotColor(key: string, index: number): string {
  if (key.includes('support') || key.includes('value-area-low')) return '#20c997';
  if (key.includes('resistance') || key.includes('value-area-high')) return '#ff6b6b';
  if (key.includes('histogram')) return '#20c997';
  if (key.includes('signal')) return '#ff922b';
  if (key.includes('upper') || key.includes('lower')) return '#74c0fc';
  if (key.includes('middle')) return '#a5d8ff';
  if (key.startsWith('sma') || key.startsWith('vwap')) return '#ffd43b';
  if (key.startsWith('ema')) return '#e599f7';
  if (key.startsWith('bull-market-band:sma')) return '#ff6b6b';
  if (key.startsWith('bull-market-band:ema')) return '#40ad50';
  return plotColors[index % plotColors.length];
}

function copyStyle(style: CoreIndicatorStyle | undefined): CoreIndicatorStyle | undefined {
  if (!style) return undefined;
  return {
    ...style,
    plots: style.plots ? { ...style.plots } : undefined,
    colors: style.colors ? { ...style.colors } : undefined,
    lineStyles: style.lineStyles ? { ...style.lineStyles } : undefined,
  };
}

function defaultPeriod(id: CoreIndicatorId): number {
  if (id === 'rsi' || id === 'atr' || id === 'rsi-divergence' || id === 'stochastic-rsi') return 14;
  if (id === 'macd' || id === 'log-macd' || id === 'macd-dema') return 9;
  if (id === 'death-cross' || id === 'golden-cross') return 50;
  if (id === 'ema-stack') return 9;
  if (id === 'volume-profile') return 100;
  if (id === 'swing-liquidity') return 5;
  if (id === 'fair-value-gap') return 3;
  if (id === 'ideal-bb') return 120;
  return 20;
}

function resetIndicator(indicator: CoreIndicatorInstance): CoreIndicatorInstance {
  const period = defaultPeriod(indicator.id);
  const reset: CoreIndicatorInstance = { ...indicator, period, visible: true, style: undefined };
  if (indicator.id === 'macd' || indicator.id === 'log-macd' || indicator.id === 'macd-dema') {
    reset.fastPeriod = 12;
    reset.slowPeriod = 26;
    reset.signalPeriod = 9;
  }
  if (indicator.id === 'bollinger') reset.standardDeviations = 2;
  if (indicator.id === 'bull-market-band') {
    reset.fastPeriod = 20;
    reset.slowPeriod = 21;
  }
  if (indicator.id === 'death-cross' || indicator.id === 'golden-cross') {
    reset.fastPeriod = 50;
    reset.slowPeriod = 200;
  }
  if (indicator.id === 'rsi-divergence') reset.fastPeriod = 5;
  if (indicator.id === 'stochastic-rsi') {
    reset.fastPeriod = 3;
    reset.signalPeriod = 3;
  }
  if (indicator.id === 'vwap') reset.anchorTime = null;
  return reset;
}

function numberOr(current: number | undefined, value: string, minimum = 1): number | undefined {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return current;
  return Math.max(minimum, parsed);
}

function Field({
  label,
  value,
  min = 1,
  step = 1,
  onChange,
}: {
  label: string;
  value: number | undefined;
  min?: number;
  step?: number;
  onChange: (value: string) => void;
}) {
  return (
    <label className="trading-indicator-settings-field">
      <span>{label}</span>
      <input type="number" min={min} step={step} value={value ?? ''} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function TradingIndicatorSettings({
  indicator,
  onApply,
  onClose,
}: {
  indicator: CoreIndicatorInstance;
  onApply: (patch: Partial<CoreIndicatorInstance>) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<SettingsTab>('inputs');
  const [draft, setDraft] = useState<CoreIndicatorInstance>(() => ({ ...indicator, style: copyStyle(indicator.style) }));
  const plots = useMemo(() => indicatorPlotDefinitions(draft), [draft]);
  const style = draft.style;
  const setNumber = (key: 'period' | 'fastPeriod' | 'slowPeriod' | 'signalPeriod' | 'standardDeviations', value: string, minimum = 1) => {
    const next = numberOr(undefined, value, minimum);
    setDraft((current) => ({ ...current, [key]: next === undefined ? current[key] : key === 'standardDeviations' ? next : Math.round(next) }));
  };
  const setStyle = (patch: CoreIndicatorStyle) => {
    setDraft((current) => ({
      ...current,
      style: {
        ...current.style,
        ...patch,
        plots: patch.plots ? { ...current.style?.plots, ...patch.plots } : current.style?.plots,
        colors: patch.colors ? { ...current.style?.colors, ...patch.colors } : current.style?.colors,
        lineStyles: patch.lineStyles ? { ...current.style?.lineStyles, ...patch.lineStyles } : current.style?.lineStyles,
      },
    }));
  };

  const inputContent = (() => {
    if (draft.id === 'bull-market-band') {
      return (
        <>
          <div className="trading-indicator-settings-section-label">Calculation</div>
          <label className="trading-indicator-settings-field">
            <span>Timeframe</span>
            <select value="1w" disabled><option value="1w">1 week</option></select>
          </label>
          <p className="trading-indicator-settings-help">This indicator uses weekly closes for its moving averages.</p>
          <Field label="20W SMA period" value={draft.fastPeriod ?? 20} onChange={(value) => setNumber('fastPeriod', value)} />
          <Field label="21W EMA period" value={draft.slowPeriod ?? 21} onChange={(value) => setNumber('slowPeriod', value)} />
        </>
      );
    }
    return (
      <>
        <div className="trading-indicator-settings-section-label">Calculation</div>
        {!['vwap', 'ideal-bb', 'ema-stack'].includes(draft.id) ? (
          <Field label="Period" value={draft.period} onChange={(value) => setNumber('period', value)} />
        ) : null}
        {draft.id === 'bollinger' ? <Field label="Standard deviations" value={draft.standardDeviations ?? 2} min={0.1} step={0.1} onChange={(value) => setNumber('standardDeviations', value, 0.1)} /> : null}
        {['macd', 'log-macd', 'macd-dema'].includes(draft.id) ? (
          <>
            <Field label="Fast period" value={draft.fastPeriod ?? 12} onChange={(value) => setNumber('fastPeriod', value)} />
            <Field label="Slow period" value={draft.slowPeriod ?? 26} onChange={(value) => setNumber('slowPeriod', value)} />
            <Field label="Signal period" value={draft.signalPeriod ?? 9} onChange={(value) => setNumber('signalPeriod', value)} />
          </>
        ) : null}
        {draft.id === 'rsi-divergence' ? <Field label="Fast RSI period" value={draft.fastPeriod ?? 5} onChange={(value) => setNumber('fastPeriod', value)} /> : null}
        {draft.id === 'stochastic-rsi' ? (
          <>
            <Field label="%K smoothing" value={draft.fastPeriod ?? 3} onChange={(value) => setNumber('fastPeriod', value)} />
            <Field label="%D smoothing" value={draft.signalPeriod ?? 3} onChange={(value) => setNumber('signalPeriod', value)} />
          </>
        ) : null}
        {draft.id === 'death-cross' || draft.id === 'golden-cross' ? (
          <>
            <Field label="Fast period" value={draft.fastPeriod ?? 50} onChange={(value) => setNumber('fastPeriod', value)} />
            <Field label="Slow period" value={draft.slowPeriod ?? 200} onChange={(value) => setNumber('slowPeriod', value)} />
          </>
        ) : null}
        {draft.id === 'vwap' ? (
          <label className="trading-indicator-settings-field">
            <span>Anchor time</span>
            <input type="datetime-local" value={draft.anchorTime ? draft.anchorTime.slice(0, 16) : ''} onChange={(event) => setDraft((current) => ({ ...current, anchorTime: event.target.value ? new Date(event.target.value).toISOString() : null }))} />
          </label>
        ) : null}
        {['ema-stack', 'ideal-bb', 'fair-value-gap'].includes(draft.id) ? <p className="trading-indicator-settings-help">This community indicator uses a fixed calculation profile. Its plots can be customized in Style.</p> : null}
      </>
    );
  })();

  return (
    <div className="trading-indicator-settings-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="trading-indicator-settings" role="dialog" aria-modal="true" aria-labelledby="trading-indicator-settings-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="trading-indicator-settings-header">
          <h2 id="trading-indicator-settings-title">{titleFor(draft)}</h2>
          <button type="button" className="trading-indicator-settings-close" aria-label="Close indicator settings" onClick={onClose}>×</button>
        </header>
        <nav className="trading-indicator-settings-tabs" role="tablist" aria-label="Indicator settings sections">
          {(['inputs', 'style', 'visibility'] as SettingsTab[]).map((item) => (
            <button key={item} type="button" role="tab" aria-selected={tab === item} className={tab === item ? 'active' : undefined} onClick={() => setTab(item)}>
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </nav>
        <div className="trading-indicator-settings-body">
          {tab === 'inputs' ? inputContent : null}
          {tab === 'style' ? (
            <>
              <div className="trading-indicator-settings-section-label">Plots</div>
              <div className="trading-indicator-settings-plot-list">
                {plots.map((plot, index) => (
                  <div className="trading-indicator-settings-plot" key={plot.key}>
                    <label>
                      <input type="checkbox" checked={style?.plots?.[plot.key] !== false} onChange={(event) => setStyle({ plots: { [plot.key]: event.target.checked } })} />
                      <span>{plot.title}</span>
                    </label>
                    <div className="trading-indicator-settings-plot-actions">
                      <input aria-label={`${plot.title} color`} type="color" value={style?.colors?.[plot.key] ?? defaultPlotColor(plot.key, index)} onChange={(event) => setStyle({ colors: { [plot.key]: event.target.value } })} />
                      <select aria-label={`${plot.title} line style`} value={style?.lineStyles?.[plot.key] ?? 'solid'} onChange={(event) => setStyle({ lineStyles: { [plot.key]: event.target.value as IndicatorLineStyle } })}>
                        {lineStyleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </div>
                  </div>
                ))}
              </div>
              {supportsBackground(draft.id, plots.length) ? (
                <div className="trading-indicator-settings-plot">
                  <label>
                    <input type="checkbox" checked={style?.backgroundVisible !== false} onChange={(event) => setStyle({ backgroundVisible: event.target.checked })} />
                    <span>Plots Background</span>
                  </label>
                  <input aria-label="Plots background color" type="color" value={style?.backgroundColor ?? indicatorDefaultBackgroundColor(draft.id)} onChange={(event) => setStyle({ backgroundColor: event.target.value })} />
                </div>
              ) : null}
              <div className="trading-indicator-settings-section-label">Output values</div>
              <label className="trading-indicator-settings-field">
                <span>Precision</span>
                <select value={style?.precision === null || style?.precision === undefined ? 'default' : String(style.precision)} onChange={(event) => setStyle({ precision: event.target.value === 'default' ? null : Number(event.target.value) })}>
                  <option value="default">Default</option>
                  {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((value) => <option key={value} value={value}>{value} decimal{value === 1 ? '' : 's'}</option>)}
                </select>
              </label>
              <label className="trading-indicator-settings-check"><input type="checkbox" checked={style?.labelsOnPriceScale === true} onChange={(event) => setStyle({ labelsOnPriceScale: event.target.checked })} /><span>Show price levels</span></label>
              <label className="trading-indicator-settings-check"><input type="checkbox" checked={style?.valuesInStatusLine !== false} onChange={(event) => setStyle({ valuesInStatusLine: event.target.checked })} /><span>Values in status line</span></label>
              <div className="trading-indicator-settings-section-label">Input values</div>
              <label className="trading-indicator-settings-check"><input type="checkbox" checked={style?.inputsInStatusLine !== false} onChange={(event) => setStyle({ inputsInStatusLine: event.target.checked })} /><span>Inputs in status line</span></label>
              <label className="trading-indicator-settings-field">
                <span>Line width</span>
                <select value={String(style?.lineWidth ?? 2)} onChange={(event) => setStyle({ lineWidth: Number(event.target.value) as 1 | 2 | 3 | 4 })}>
                  <option value="1">1 px</option><option value="2">2 px</option><option value="3">3 px</option><option value="4">4 px</option>
                </select>
              </label>
            </>
          ) : null}
          {tab === 'visibility' ? (
            <>
              <div className="trading-indicator-settings-section-label">Visibility</div>
              <label className="trading-indicator-settings-check"><input type="checkbox" checked={draft.visible !== false} onChange={(event) => setDraft((current) => ({ ...current, visible: event.target.checked }))} /><span>Show indicator on chart</span></label>
              <p className="trading-indicator-settings-help">Hidden indicators stay configured and can be shown again from the indicator controls.</p>
            </>
          ) : null}
        </div>
        <footer className="trading-indicator-settings-footer">
          <button type="button" className="trading-indicator-settings-defaults" onClick={() => setDraft(resetIndicator(draft))}>Defaults</button>
          <div>
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="button" className="primary" onClick={() => { onApply(draft); onClose(); }}>OK</button>
          </div>
        </footer>
      </section>
    </div>
  );
}
