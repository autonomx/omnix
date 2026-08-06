import { useEffect, useMemo } from 'react';
import { TradingChartPanel } from './TradingChartPanel';
import { TradingChartSynchronization } from './chart/chartSynchronization';
import { useTradingStore } from './tradingStore';

export function TradingChartGrid() {
  const layout = useTradingStore((state) => state.layout);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const links = useTradingStore((state) => state.links);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const synchronization = useMemo(() => new TradingChartSynchronization(), []);
  const activeIndex = Math.max(0, charts.findIndex((chart) => chart.chartId === activeChartId));
  const visibleCharts = layout === 'one'
    ? charts.slice(activeIndex, activeIndex + 1)
    : layout === 'four'
      ? charts.slice(0, 4)
      : charts.slice(activeIndex, activeIndex + 2).length === 2
        ? charts.slice(activeIndex, activeIndex + 2)
        : charts.slice(0, 2);

  useEffect(() => {
    synchronization.setLinks({ crosshair: links.crosshair, visibleRange: links.visibleRange });
  }, [links.crosshair, links.visibleRange, synchronization]);

  useEffect(() => () => synchronization.dispose(), [synchronization]);

  return (
    <section className={`trading-chart-grid layout-${layout}`} aria-label={`${layout} Trading chart layout`}>
      {visibleCharts.map((chart) => (
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
            synchronization={synchronization}
          />
        </div>
      ))}
    </section>
  );
}
