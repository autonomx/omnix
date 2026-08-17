import type { TradingIndicatorPaneGeometry } from './chart/chartAdapter';
import type { CoreIndicatorId } from './indicators/coreIndicators';
import type { TradingIndicatorMove } from './tradingStore';

export function TradingIndicatorPaneControls({
  indicator,
  geometry,
  minimized,
  canMoveUp,
  canMoveDown,
  onToggleMinimized,
  onSettings,
  onMove,
  onClose,
}: {
  indicator: { id: CoreIndicatorId; period: number };
  geometry: TradingIndicatorPaneGeometry;
  minimized: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onToggleMinimized: () => void;
  onSettings: () => void;
  onMove: (direction: TradingIndicatorMove) => void;
  onClose: () => void;
}) {
  const label = `${indicator.id.toUpperCase()} ${indicator.period}`;
  return (
    <div
      className="trading-indicator-pane-controls"
      style={{ top: Math.max(2, geometry.top + 4) }}
      onPointerDown={(event) => event.stopPropagation()}
      data-indicator-id={indicator.id}
      data-minimized={minimized}
    >
      <span className="trading-indicator-pane-label">{label}</span>
      <button type="button" title={`Move ${label} panel up`} aria-label={`Move ${label} panel up`} disabled={!canMoveUp} onClick={() => onMove('up')}>↑</button>
      <button type="button" title={`Move ${label} panel down`} aria-label={`Move ${label} panel down`} disabled={!canMoveDown} onClick={() => onMove('down')}>↓</button>
      <button
        type="button"
        title={minimized ? `Restore ${label} panel` : `Minimize ${label} panel`}
        aria-label={minimized ? `Restore ${label} panel` : `Minimize ${label} panel`}
        aria-expanded={!minimized}
        onClick={onToggleMinimized}
      >
        {minimized ? '⌃' : '⌄'}
      </button>
      <button type="button" title={`Open ${label} settings`} aria-label={`Open ${label} settings`} onClick={onSettings}>⚙</button>
      <button type="button" title={`Close ${label} panel`} aria-label={`Close ${label} panel`} onClick={onClose}>×</button>
    </div>
  );
}
