import { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ChartPanelLegend } from './TradingChartPanelLegend';
import { INDICATOR_LEGEND_STARTS_COLLAPSED } from './useTradingChartPanelState';
import type { TradingChartPanelModel } from './useTradingChartPanel';

afterEach(cleanup);

function Legend() {
  const [indicatorLegendCollapsed, setIndicatorLegendCollapsed] = useState(INDICATOR_LEGEND_STARTS_COLLAPSED);
  const legendIndicators = [{ id: 'sma', period: 20, visible: true }, { id: 'ema', period: 9, visible: true }];
  const ws = {
    comparisons: [], legendComparisons: [], legendCount: legendIndicators.length, legendIndicators,
    indicatorLegendCollapsed, setIndicatorLegendCollapsed,
    onOpenPineScript: vi.fn(), onToggleIndicator: vi.fn(), onToggleIndicatorVisibility: vi.fn(),
    onUpdateComparisons: vi.fn(), setCompareDialogOpen: vi.fn(), setSettingsIndicator: vi.fn(),
  } as unknown as TradingChartPanelModel;
  return <ChartPanelLegend ws={ws} />;
}

it('starts minimized to its count and opens on the toggle', () => {
  render(<Legend />);
  const toggle = screen.getByRole('button', { name: 'Expand indicator legend' });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(toggle).toHaveTextContent('2');
  expect(screen.queryByText('SMA 20')).toBeNull();

  fireEvent.click(toggle);
  expect(screen.getByText('SMA 20')).toBeInTheDocument();
  expect(screen.getByText('EMA 9')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Collapse indicator legend' })).toHaveAttribute('aria-expanded', 'true');
});
