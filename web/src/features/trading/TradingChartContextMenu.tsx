import { useEffect, useState } from 'react';
import type { ChartAlertPlacement } from './drawings/TradingDrawingOverlay';
import './TradingChartContextMenu.css';

function displayPrice(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const digits = Math.abs(value) >= 1_000 ? 2 : Math.abs(value) >= 1 ? 4 : 6;
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function TradingChartContextMenu({
  point,
  symbol,
  indicatorContext,
  drawingCount,
  indicatorCount,
  cursorLocked,
  tableVisible,
  onClose,
  onReset,
  onCopyPrice,
  onPastePrice,
  onAddAlert,
  onToggleCursor,
  onToggleTable,
  onObjectTree,
  onApplyTemplate,
  onRemoveDrawings,
  onRemoveIndicators,
  onSettings,
}: {
  point: ChartAlertPlacement;
  symbol: string;
  indicatorContext: boolean;
  drawingCount: number;
  indicatorCount: number;
  cursorLocked: boolean;
  tableVisible: boolean;
  onClose: () => void;
  onReset: () => void;
  onCopyPrice: () => void;
  onPastePrice: () => void;
  onAddAlert: (() => void) | null;
  onToggleCursor: () => void;
  onToggleTable: () => void;
  onObjectTree: () => void;
  onApplyTemplate: (template: 'default' | 'clean' | 'momentum') => void;
  onRemoveDrawings: () => void;
  onRemoveIndicators: () => void;
  onSettings: () => void;
}) {
  const [templateOpen, setTemplateOpen] = useState(false);

  useEffect(() => {
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('.trading-chart-context-menu')) return;
      onClose();
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('pointerdown', close, true);
    window.addEventListener('keydown', keydown);
    return () => {
      document.removeEventListener('pointerdown', close, true);
      window.removeEventListener('keydown', keydown);
    };
  }, [onClose]);

  const action = (callback: () => void) => () => {
    callback();
    onClose();
  };

  return (
    <div
      className="trading-chart-context-menu"
      role="menu"
      aria-label="Chart context menu"
      style={{ left: point.x, top: point.y }}
      onPointerDown={(event) => event.stopPropagation()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <button type="button" role="menuitem" onClick={action(onReset)}>↻ <span>Reset {indicatorContext ? `${symbol} pane` : 'chart'} view</span><kbd>Alt + R</kbd></button>
      <button type="button" role="menuitem" onClick={action(onCopyPrice)}>⧉ <span>Copy {indicatorContext ? 'value' : 'price'} {displayPrice(point.price)}</span></button>
      <button type="button" role="menuitem" onClick={action(onPastePrice)}>▣ <span>Paste</span><kbd>Ctrl + V</kbd></button>
      <div className="trading-context-menu-separator" />
      <button type="button" role="menuitem" disabled={!onAddAlert} onClick={onAddAlert ? action(onAddAlert) : undefined}>◷ <span>{onAddAlert ? `Add alert on ${symbol} at ${displayPrice(point.price)}` : `Alerts unavailable for ${symbol}`}</span>{onAddAlert ? <kbd>Alt + A</kbd> : null}</button>
      <button type="button" role="menuitemcheckbox" aria-checked={cursorLocked} onClick={action(onToggleCursor)}>⌖ <span>Lock vertical cursor line by time</span></button>
      <div className="trading-context-menu-separator" />
      <button type="button" role="menuitemcheckbox" aria-checked={tableVisible} onClick={action(onToggleTable)}>▤ <span>Table view</span></button>
      <button type="button" role="menuitem" onClick={action(onObjectTree)}>◇ <span>Object tree</span></button>
      <div className="trading-context-menu-submenu-wrap">
        <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={templateOpen} onClick={() => setTemplateOpen((value) => !value)}>◈ <span>Chart template</span><b>›</b></button>
        {templateOpen ? (
          <div className="trading-chart-context-submenu" role="menu" aria-label="Chart templates">
            <button type="button" role="menuitem" onClick={action(() => onApplyTemplate('default'))}>Default</button>
            <button type="button" role="menuitem" onClick={action(() => onApplyTemplate('clean'))}>Clean chart</button>
            <button type="button" role="menuitem" onClick={action(() => onApplyTemplate('momentum'))}>Momentum studies</button>
          </div>
        ) : null}
      </div>
      <div className="trading-context-menu-separator" />
      <button type="button" role="menuitem" disabled={drawingCount === 0} onClick={action(onRemoveDrawings)}>⌫ <span>Remove {drawingCount} drawings</span></button>
      <button type="button" role="menuitem" disabled={indicatorCount === 0} onClick={action(onRemoveIndicators)}>⌫ <span>Remove {indicatorCount} indicators</span></button>
      <div className="trading-context-menu-separator" />
      <button type="button" role="menuitem" onClick={action(onSettings)}>⚙ <span>Settings…</span></button>
    </div>
  );
}
