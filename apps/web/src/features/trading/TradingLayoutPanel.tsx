import { TradingDiagnosticsPanel } from './TradingDiagnosticsPanel';
import type { DrawingSnapMode } from './drawings/drawingCommands';
import type { TradingLayout, TradingLinkState } from './tradingStore';

const layouts: Array<{ id: TradingLayout; label: string; glyph: string }> = [
  { id: 'one', label: 'Single chart', glyph: '□' },
  { id: 'two-horizontal', label: 'Two columns', glyph: '▥' },
  { id: 'two-vertical', label: 'Two rows', glyph: '▤' },
  { id: 'four', label: 'Four charts', glyph: '▦' },
];

export function TradingLayoutPanel({
  layout,
  links,
  snapMode,
  onSetLayout,
  onSetLink,
  onSetSnapMode,
}: {
  layout: TradingLayout;
  links: TradingLinkState;
  snapMode: DrawingSnapMode;
  onSetLayout: (layout: TradingLayout) => void;
  onSetLink: (key: keyof TradingLinkState, enabled: boolean) => void;
  onSetSnapMode: (mode: DrawingSnapMode) => void;
}) {
  return (
    <section className="trading-layout-panel" aria-label="Trading layout settings">
      <div className="trading-layout-options" role="radiogroup" aria-label="Chart layout">
        {layouts.map((item) => (
          <button
            key={item.id}
            type="button"
            role="radio"
            aria-checked={layout === item.id}
            className={layout === item.id ? 'active' : undefined}
            onClick={() => onSetLayout(item.id)}
          >
            <span aria-hidden="true">{item.glyph}</span>
            <small>{item.label}</small>
          </button>
        ))}
      </div>

      <fieldset>
        <legend>Chart linking</legend>
        {(Object.keys(links) as Array<keyof TradingLinkState>).map((key) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={links[key]}
              onChange={(event) => onSetLink(key, event.target.checked)}
            />
            <span>{key === 'visibleRange' ? 'Visible range' : key}</span>
          </label>
        ))}
      </fieldset>

      <label className="trading-layout-snap">
        Drawing snap
        <select
          aria-label="Drawing snap mode"
          value={snapMode}
          onChange={(event) => onSetSnapMode(event.target.value as DrawingSnapMode)}
        >
          {(['none', 'time', 'price', 'ohlc'] as DrawingSnapMode[]).map((item) => (
            <option key={item} value={item}>{item.toUpperCase()}</option>
          ))}
        </select>
      </label>

      <details className="trading-layout-diagnostics">
        <summary>Data diagnostics</summary>
        <TradingDiagnosticsPanel />
      </details>
    </section>
  );
}
