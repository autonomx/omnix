import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { COPILOT_SUGGESTIONS, TradingCopilotPanel, copilotRequest, type CopilotChart } from './TradingCopilotPanel';
import { applyCopilotAction, indicatorsWith, indicatorsWithout, type CopilotChartControls } from './copilotActions';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';
import type { CopilotAction, CopilotResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const indicators: CoreIndicatorInstance[] = [
  { id: 'sma', period: 20, enabled: true, visible: true },
  { id: 'rsi', period: 14, enabled: false, visible: false },
  { id: 'ema', period: 9, enabled: true, visible: true, source: { indicatorId: 'sma' } } as CoreIndicatorInstance,
];

function action(fields: Partial<CopilotAction> & Pick<CopilotAction, 'id' | 'kind' | 'label'>): CopilotAction {
  return { interval: null, indicator: null, period: null, price: null, time: null, start: null, end: null, note: null, ...fields };
}

const result: CopilotResult = {
  reply: 'Support sits near 98; the trend is up.',
  points: ['Higher lows since Tuesday.'],
  actions: [
    action({ id: 'a1', kind: 'set_interval', label: 'Switch to 4h', interval: '4h' }),
    action({ id: 'a2', kind: 'draw_level', label: 'Draw level 98 · support', price: '98.00', time: '2026-11-20T15:00:00Z', note: 'support' }),
    action({ id: 'a3', kind: 'mark_range', label: 'Mark range', start: '2026-11-19T09:00:00Z', end: '2026-11-20T09:00:00Z' }),
  ],
  actions_dropped: 1,
  headlines: [{ id: 'h1', headline: 'ETF inflows surge', source: 'benzinga', url: 'https://news.example/1', created_at: '2026-11-20T10:00:00Z' }],
  facts: {
    bars: 50, change: '2', change_percent: '2.0', close: '102', open: '100', high: '103', low: '97', volume: '12500', volume_vs_prior: null,
    first_bar: '2026-11-18T09:00:00Z', last_bar: '2026-11-20T15:00:00Z', high_time: '2026-11-20T14:00:00Z', low_time: '2026-11-18T09:00:00Z',
    largest_up_bar: null, largest_down_bar: null, prior_change_percent: null, rsi_14_start: null, rsi_14_end: null,
    sma_20_start: null, sma_20_end: null, sma_50_end: null, ema_20_end: null,
  },
  news_status: 'ok', provider: 'claude', model: 'haiku', read_only: true,
  disclaimer: 'Research only. Not financial advice. No order was created or executed.',
};

function controls() {
  return {
    instrumentId: 'crypto:BTC/USD',
    indicators,
    onSetInterval: vi.fn<CopilotChartControls['onSetInterval']>(),
    onSetIndicators: vi.fn<CopilotChartControls['onSetIndicators']>(),
    addDrawing: vi.fn<CopilotChartControls['addDrawing']>(),
  };
}

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('Copilot chart actions', () => {
  it('turns an indicator on, adds a missing one with its defaults, and frees what read a removed one', () => {
    expect(indicatorsWith(indicators, 'rsi', 21).find((item) => item.id === 'rsi')).toMatchObject({ enabled: true, visible: true, period: 21 });
    expect(indicatorsWith(indicators, 'macd', null).at(-1)).toMatchObject({ id: 'macd', enabled: true });
    const removed = indicatorsWithout(indicators, 'sma');
    expect(removed[0]).toMatchObject({ enabled: false, visible: false });
    expect(removed[2].source).toBeNull();
  });

  it('applies each kind to the chart it was given and refuses an incomplete one', () => {
    const chart = controls();
    expect(applyCopilotAction(result.actions[0], chart, 102)).toBe(true);
    expect(chart.onSetInterval).toHaveBeenCalledWith('4h');
    expect(applyCopilotAction(result.actions[1], chart, 102)).toBe(true);
    expect(chart.addDrawing.mock.calls[0][0]).toMatchObject({ toolType: 'horizontal-line', points: [{ time: '2026-11-20T15:00:00Z', price: 98 }], text: 'support', instrumentId: 'crypto:BTC/USD' });
    expect(applyCopilotAction(result.actions[2], chart, 102)).toBe(true);
    expect(chart.addDrawing.mock.calls[1][0]).toMatchObject({ toolType: 'ai-range', points: [{ time: '2026-11-19T09:00:00Z', price: 102 }, { time: '2026-11-20T09:00:00Z', price: 102 }] });
    expect(applyCopilotAction(action({ id: 'a9', kind: 'add_indicator', label: 'Add', indicator: 'ema', period: 50 }), chart, 102)).toBe(true);
    expect(chart.onSetIndicators.mock.calls[0][0][2]).toMatchObject({ id: 'ema', period: 50, enabled: true });
    expect(applyCopilotAction(action({ id: 'a8', kind: 'draw_level', label: 'Draw', price: 'NaN', time: '2026-11-20T15:00:00Z' }), chart, 102)).toBe(false);
    expect(applyCopilotAction(action({ id: 'a7', kind: 'set_interval', label: 'Switch' }), chart, 102)).toBe(false);
  });
});

describe('TradingCopilotPanel', () => {
  const chart: CopilotChart = { ...controls(), bindingId: 'b1', interval: '1h', supportedIntervals: ['1h', '4h', '1d'] };

  it('sends the enabled indicators, the intervals and at most 16 messages', () => {
    const many = Array.from({ length: 20 }, (_, index) => ({ role: index % 2 ? 'assistant' : 'user', content: `m${index}` }) as const);
    const request = copilotRequest(chart, many);
    expect(request.messages).toHaveLength(16);
    expect(request.messages.at(-1)?.content).toBe('m19');
    expect(request.indicators).toEqual([{ id: 'sma', period: 20 }, { id: 'ema', period: 9 }]);
    expect(request.supported_intervals).toEqual(['1h', '4h', '1d']);
  });

  it('asks, shows the answer with its cited headlines, and applies a proposal only when chosen, once', async () => {
    const copilot = vi.spyOn(tradingResearchApi, 'copilot').mockResolvedValue(result);
    const own = controls();
    render(wrap(<TradingCopilotPanel chart={{ ...chart, onSetInterval: own.onSetInterval }} addDrawing={own.addDrawing} />));

    fireEvent.click(screen.getByRole('button', { name: COPILOT_SUGGESTIONS[0] }));
    expect(await screen.findByText('Support sits near 98; the trend is up.')).toBeTruthy();
    expect(copilot.mock.calls[0][0]).toMatchObject({ instrument_id: 'crypto:BTC/USD', interval: '1h', messages: [{ role: 'user', content: COPILOT_SUGGESTIONS[0] }] });
    expect(screen.getByRole('link', { name: 'ETF inflows surge' }).getAttribute('href')).toBe('https://news.example/1');
    expect(own.onSetInterval).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '+ Switch to 4h' }));
    expect(own.onSetInterval).toHaveBeenCalledWith('4h');
    expect((screen.getByRole('button', { name: '✓ Switch to 4h' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '+ Mark range' }));
    expect(own.addDrawing.mock.calls[0][0].points[0].price).toBe(102);

    // The follow-up carries the conversation so far, the answer as the assistant's turn.
    fireEvent.change(screen.getByLabelText('Ask Copilot'), { target: { value: 'And resistance?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(copilot).toHaveBeenCalledTimes(2));
    expect(copilot.mock.calls[1][0].messages).toEqual([
      { role: 'user', content: COPILOT_SUGGESTIONS[0] },
      { role: 'assistant', content: result.reply },
      { role: 'user', content: 'And resistance?' },
    ]);
  });

  it('shows a failure and starts over on New chat', async () => {
    vi.spyOn(tradingResearchApi, 'copilot').mockRejectedValue(new Error('Copilot request failed (503): unavailable'));
    render(wrap(<TradingCopilotPanel chart={chart} addDrawing={vi.fn()} />));
    fireEvent.change(screen.getByLabelText('Ask Copilot'), { target: { value: 'Trend?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect((await screen.findByRole('alert')).textContent).toContain('503');
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('button', { name: COPILOT_SUGGESTIONS[1] })).toBeTruthy();
  });
});
