import { downloadUrl } from '../../shared/download';
import { convertedPrice, intervalLabel } from './tradingChartPanelModel';
import type { TradingChartPanelModel } from './useTradingChartPanel';
import { chartPalette } from './chartPalette';
import { DrawingPropertiesButton } from './drawings/DrawingPropertiesButton';
import { drawingToolDefinition } from './drawings/tools/registry';

/** The chart's header: symbol, quote, interval and chart controls. */
export function ChartPanelHeader({ ws }: { ws: TradingChartPanelModel }) {
  const {
    active, adapterRef, change, changePercent, chartFocusMode, chartId, chartNumber, chartQuery, direction, drawings,
    instrumentId, interval, latest, onOpenSymbolSearch, priceScaleMultiplier, provenance, resolvedBinding,
    selectedDrawing, setCompareDialogOpen, streamStatus, toggleFullscreen,
  } = ws;
  return (
    <>
      <header className="trading-chart-header">
        <div className="trading-chart-heading">
          <div className="trading-chart-title-row">
            <button
              type="button"
              className="trading-chart-symbol-trigger"
              aria-label={`Change symbol for Chart ${chartNumber}`}
              title={`Change symbol for Chart ${chartNumber}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={onOpenSymbolSearch}
            >
              <strong>{chartQuery.data?.instrument.display_symbol ?? instrumentId}</strong>
              <span aria-hidden="true">⌄</span>
            </button>
            <button
              type="button"
              className="trading-compare-trigger"
              aria-label="Compare another symbol"
              title="Compare another symbol"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => setCompareDialogOpen(true)}
            >+</button>
            <span>· {intervalLabel(interval)} · {chartQuery.data?.instrument.venue ?? resolvedBinding?.provider ?? 'Omnix'}</span>
            <i className={`trading-stream-dot ${streamStatus}`} role="img" aria-label={`Feed ${streamStatus}`} />
          </div>
          {latest ? (
            <div className="trading-chart-ohlc">
              <span>O <b>{convertedPrice(latest.open, priceScaleMultiplier)}</b></span>
              <span>H <b>{convertedPrice(latest.high, priceScaleMultiplier)}</b></span>
              <span>L <b>{convertedPrice(latest.low, priceScaleMultiplier)}</b></span>
              <span>C <b>{convertedPrice(latest.close, priceScaleMultiplier)}</b></span>
              <span className={direction}>{change >= 0 ? '+' : ''}{convertedPrice(change, priceScaleMultiplier)} ({changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%)</span>
            </div>
          ) : null}
        </div>

        <div
          className="trading-chart-provenance"
          title={`${resolvedBinding?.provider ?? 'Resolving provider'} · ${resolvedBinding?.is_official_api ? 'official API' : 'unofficial API'} · ${provenance?.freshness_mode ?? 'loading'}`}
        >
          <span>{resolvedBinding?.provider ?? 'resolving'}</span>
          <span className={`stream-${streamStatus}`}>{streamStatus}</span>
          <button
            type="button"
            className="trading-chart-fullscreen"
            aria-label={chartFocusMode ? 'Exit chart focus mode' : 'Focus this chart'}
            aria-pressed={chartFocusMode}
            title={chartFocusMode ? 'Show all charts' : 'Focus this chart'}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => void toggleFullscreen()}
          >
            {chartFocusMode ? '↙' : '⛶'}
          </button>
        </div>

        {active ? (
          <div className="trading-drawing-manager" onPointerDown={(event) => event.stopPropagation()}>
            <button type="button" onClick={() => drawings.undo()} aria-label="Undo drawing">↶</button>
            <button type="button" onClick={() => drawings.redo()} aria-label="Redo drawing">↷</button>
            <button type="button" onClick={() => adapterRef.current && downloadUrl(adapterRef.current.snapshotDataUrl(), `${chartId}.png`)} aria-label="Snapshot chart">PNG</button>
            {drawings.hasConflict ? (
              <>
                <span role="status">Drawing conflict</span>
                <button type="button" onClick={() => void drawings.resolveConflict('reload')}>Reload server</button>
                <button type="button" onClick={() => void drawings.resolveConflict('overwrite')}>Overwrite server</button>
              </>
            ) : null}
            {selectedDrawing ? (
              <>
                <input aria-label="Drawing color" type="color" value={selectedDrawing.style?.color ?? chartPalette.cyan} onChange={(event) => drawings.updateSelected({ style: { ...(selectedDrawing.style ?? { lineWidth: 2, lineStyle: 'solid' }), color: event.target.value } })} />
                <button type="button" aria-pressed={Boolean(selectedDrawing.locked)} onClick={() => drawings.updateSelected({ locked: !selectedDrawing.locked })}>{selectedDrawing.locked ? 'Unlock' : 'Lock'}</button>
                <button type="button" aria-pressed={Boolean(selectedDrawing.hidden)} onClick={() => drawings.updateSelected({ hidden: !selectedDrawing.hidden })}>{selectedDrawing.hidden ? 'Show' : 'Hide'}</button>
                {drawingToolDefinition(selectedDrawing.toolType)?.editableText ? <input aria-label="Drawing text" type="text" value={selectedDrawing.text ?? ''} onChange={(event) => drawings.updateSelected({ text: event.target.value })} /> : null}
                <DrawingPropertiesButton key={selectedDrawing.drawingId} drawing={selectedDrawing} onChange={(properties, mergeKey) => drawings.updateSelected({ properties }, mergeKey)} />
                <button type="button" onClick={() => drawings.removeSelected()} aria-label="Delete selected drawing">×</button>
              </>
            ) : null}
          </div>
        ) : null}
      </header>
    </>
  );
}
