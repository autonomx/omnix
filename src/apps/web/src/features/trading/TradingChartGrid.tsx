import { useEffect, useMemo, type CSSProperties } from 'react';
import { TradingChartPanel } from './TradingChartPanel';
import { TradingChartSynchronization } from './chart/chartSynchronization';
import { useTradingStore, type TradingLayout } from './tradingStore';

export function tradingGridColumns(layout: TradingLayout, chartCount: number): number {
  const forced = {
    'columns-1': 1,
    'columns-2': 2,
    'columns-3': 3,
    'columns-4': 4,
  } as const;
  if (layout !== 'auto') return forced[layout];
  return Math.max(1, Math.min(4, Math.ceil(Math.sqrt(Math.max(1, chartCount)))));
}

export function TradingChartGrid() {
  const layout = useTradingStore((state) => state.layout);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const links = useTradingStore((state) => state.links);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const updateChart = useTradingStore((state) => state.updateChart);
  const toggleIndicator = useTradingStore((state) => state.toggleIndicator);
  const setIndicators = useTradingStore((state) => state.setIndicators);
  const toggleIndicatorVisibility = useTradingStore((state) => state.toggleIndicatorVisibility);
  const moveIndicator = useTradingStore((state) => state.moveIndicator);
  const synchronization = useMemo(() => new TradingChartSynchronization(), []);
  const columns = tradingGridColumns(layout, charts.length);
  const style = { '--trading-grid-columns': columns } as CSSProperties;

  useEffect(() => {
    synchronization.setLinks({ crosshair: links.crosshair, visibleRange: links.visibleRange });
  }, [links.crosshair, links.visibleRange, synchronization]);

  useEffect(() => () => synchronization.dispose(), [synchronization]);

  return (
    <section
      className={`trading-chart-grid layout-${layout}`}
      style={style}
      aria-label={`${charts.length}-chart Trading layout with ${columns} column${columns === 1 ? '' : 's'}`}
    >
      {charts.map((chart) => (
        <div key={chart.chartId} className="trading-chart-grid-cell">
          <TradingChartPanel
            chartId={chart.chartId}
            instrumentId={chart.instrumentId}
            bindingId={chart.bindingId}
            interval={chart.interval}
            chartType={chart.chartType}
            indicators={chart.indicators}
            active={chart.chartId === activeChartId}
            onActivate={() => setActiveChart(chart.chartId)}
            onChangeInterval={(interval) => updateChart(chart.chartId, { interval })}
            onChangeChartType={(chartType) => updateChart(chart.chartId, { chartType })}
            onToggleIndicator={(id) => toggleIndicator(chart.chartId, id)}
            onClearIndicators={() => setIndicators(chart.chartId, [])}
            onToggleIndicatorVisibility={(id) => toggleIndicatorVisibility(chart.chartId, id)}
            onMoveIndicator={(id, direction) => moveIndicator(chart.chartId, id, direction)}
            synchronization={synchronization}
          />
        </div>
      ))}
    </section>
  );
}
