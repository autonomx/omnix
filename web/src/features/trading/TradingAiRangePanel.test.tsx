import { readFileSync } from 'node:fs';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradingDrawingTools } from './TradingDrawingTools';
import { AI_RANGE_PRESETS, TradingAiRangePanel, aiRangeRequest, aiRangeSpan, type AiRangeChart } from './TradingAiRangePanel';
import type { TradingChartAdapter } from './chart/chartAdapter';
import type { TradingDrawing } from './drawings/drawingCommands';
import { aiRangeTool } from './drawings/tools/definitions/aiRange';
import { drawingToolDefinition } from './drawings/tools/registry';
import type { RangeResearchResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';
import { keepsDrawingSelection } from './useTradingChartPanelLifecycle';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const chart: AiRangeChart = { instrumentId: 'crypto:BTC/USD', interval: '1h', bindingId: null, historyLimit: 1200, extendedHours: false, symbol: 'BTC/USD' };

const drawing: TradingDrawing = {
  drawingId: 'ai-1', instrumentId: chart.instrumentId, toolType: 'ai-range', selected: true, revision: 1,
  // Drawn right to left: the request still goes earliest first.
  points: [{ time: '2026-11-20T15:00:00Z', price: 101 }, { time: '2026-11-20T09:00:00Z', price: 99 }],
};

const adapter = {
  timeToCoordinate: (time: string) => (time.includes('T09') ? 100 : 300),
  indicatorPlotWidth: () => 900,
  onViewportChange: () => () => undefined,
} as unknown as TradingChartAdapter;

const result: RangeResearchResult = {
  action: 'explain', title: 'Morning rally', summary: 'Price rose 2% on rising volume.', points: ['Closed near the high.'],
  headlines: [
    { id: 'n1', headline: 'ETF inflows surge', source: 'benzinga', url: 'https://news.example/1', created_at: '2026-11-20T10:00:00Z' },
    { id: 'n2', headline: 'Odd link', source: null, url: 'javascript:alert(1)', created_at: '2026-11-20T11:00:00Z' },
  ],
  events: [],
  facts: {
    bars: 7, change: '2', change_percent: '2.0', close: '102', open: '100', high: '103', low: '99', volume: '12500', volume_vs_prior: '1.6',
    first_bar: '2026-11-20T09:00:00Z', last_bar: '2026-11-20T15:00:00Z', high_time: '2026-11-20T14:00:00Z', low_time: '2026-11-20T09:00:00Z',
    largest_up_bar: null, largest_down_bar: null, prior_change_percent: null, rsi_14_start: null, rsi_14_end: '61.2',
    sma_20_start: null, sma_20_end: null, sma_50_end: null, ema_20_end: null,
  },
  news_status: 'ok', headlines_considered: 4, provider: 'claude', model: 'haiku', read_only: true,
  disclaimer: 'Research only. Not financial advice. No order was created or executed.',
};

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('AI range tool', () => {
  it('is a registered drag tool whose band covers the full chart height', () => {
    expect(drawingToolDefinition('ai-range')?.creation.gesture).toBe('drag');
    const shapes = aiRangeTool.geometry({
      points: [{ x: 300, y: 40 }, { x: 100, y: 90 }], rawPoints: drawing.points, viewport: { width: 900, height: 480 },
      style: { color: '#2962ff', width: 2, dash: 'solid' }, selected: false, draft: false,
    } as never);
    expect(shapes[0]).toMatchObject({ kind: 'rect', x: 100, y: 0, width: 200, height: 480 });
  });

  it('has its own toolbar button that toggles the tool', () => {
    const onSelect = vi.fn();
    const { rerender } = render(<TradingDrawingTools selectedTool="cursor" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'AI range' }));
    expect(onSelect).toHaveBeenLastCalledWith('ai-range');
    rerender(<TradingDrawingTools selectedTool="ai-range" onSelect={onSelect} />);
    expect(screen.getByRole('button', { name: 'AI range' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'AI range' }));
    expect(onSelect).toHaveBeenLastCalledWith('cursor');
  });
});

describe('TradingAiRangePanel', () => {
  it('sends the chart bars request with the span earliest first', () => {
    expect(aiRangeSpan(drawing)).toEqual({ start: '2026-11-20T09:00:00Z', end: '2026-11-20T15:00:00Z' });
    expect(aiRangeRequest({ ...chart, historyLimit: 9_000 }, aiRangeSpan(drawing)!, 'ask', '  why?  ')).toEqual({
      instrument_id: chart.instrumentId, binding_id: null, interval: '1h', start: '2026-11-20T09:00:00Z', end: '2026-11-20T15:00:00Z',
      action: 'ask', question: 'why?', history_limit: 5_000, alignment: 'clock', extended_hours: false,
    });
  });

  it('offers the three presets and a question box, then shows the answer with its sources', async () => {
    const range = vi.spyOn(tradingResearchApi, 'range').mockResolvedValue(result);
    render(wrap(<TradingAiRangePanel adapter={adapter} drawing={drawing} chart={chart} onClose={vi.fn()} />));
    for (const preset of AI_RANGE_PRESETS) expect(screen.getByRole('button', { name: preset.label })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Explain this price move' }));
    expect(await screen.findByRole('heading', { name: 'Morning rally' })).toBeInTheDocument();
    expect(range.mock.calls[0][0]).toMatchObject({ action: 'explain', start: '2026-11-20T09:00:00Z', history_limit: 1200 });
    expect(screen.getByRole('link', { name: 'ETF inflows surge' })).toHaveAttribute('href', 'https://news.example/1');
    // A link Omnix can't vouch for stays text.
    expect(screen.queryByRole('link', { name: 'Odd link' })).toBeNull();
    expect(screen.getByText('Odd link')).toBeInTheDocument();
    expect(screen.getByText('+2.00%')).toBeInTheDocument();
    expect(screen.getByText(/Research only\. Not financial advice/)).toBeInTheDocument();
  });

  it('asks a free question and reports a failure', async () => {
    const range = vi.spyOn(tradingResearchApi, 'range').mockRejectedValue(new Error('AI range: the selected range has no bars'));
    render(wrap(<TradingAiRangePanel adapter={adapter} drawing={drawing} chart={chart} onClose={vi.fn()} />));
    fireEvent.change(screen.getByLabelText('Ask about this range'), { target: { value: 'Was this a breakout?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send question' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('has no bars'));
    expect(range.mock.calls[0][0]).toMatchObject({ action: 'ask', question: 'Was this a breakout?' });
  });

  it('opens beside the band and closes on request', () => {
    const onClose = vi.fn();
    render(wrap(<TradingAiRangePanel adapter={adapter} drawing={drawing} chart={chart} onClose={onClose} />));
    const panel = screen.getByRole('dialog', { name: 'AI range' });
    expect(panel.style.left).toBe('308px');
    fireEvent.click(screen.getByRole('button', { name: 'Close AI range' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('keeps its range selected when pressed, so a preset click lands (the chart deselects on any other press)', () => {
    render(wrap(<TradingAiRangePanel adapter={adapter} drawing={drawing} chart={chart} onClose={vi.fn()} />));
    expect(keepsDrawingSelection(screen.getByRole('button', { name: AI_RANGE_PRESETS[0].label }))).toBe(true);
    expect(keepsDrawingSelection(screen.getByLabelText('Ask about this range'))).toBe(true);
    expect(keepsDrawingSelection(document.body)).toBe(false);
  });

  it('sits above the chart controls and the indicator toolbar but under the alert editor', () => {
    const zIndex = (file: string, selector: string) => {
      const css = readFileSync(`src/features/trading/${file}`, 'utf8');
      const rule = css.slice(css.indexOf(`${selector}{`));
      return Number(/z-index:(\d+)/.exec(rule.slice(0, rule.indexOf('}')))?.[1]);
    };
    const panel = zIndex('TradingAiRangePanel.css', '.trading-ai-range-panel');
    expect(panel).toBeGreaterThan(zIndex('TradingYAxisControls.css', '.trading-y-axis-controls'));
    expect(panel).toBeLessThan(zIndex('TradingChartAlertOverlay.css', '.trading-chart-alert-editor-positioner'));
    expect(readFileSync('src/features/trading/TradingAiRangePanel.css', 'utf8')).toContain(":root[data-omnix-appearance='light'] .trading-ai-range-panel{");
  });
});
