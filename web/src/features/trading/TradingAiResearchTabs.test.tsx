import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CopilotResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';
import { useTradingStore } from './tradingStore';
import type { ProviderBinding } from './tradingTypes';

const drawingHook = vi.hoisted(() => ({ add: vi.fn() }));
vi.mock('./drawings/useTradingDrawings', () => ({ useTradingDrawings: () => drawingHook }));
vi.mock('./TradingResearchPanel', () => ({ TradingResearchPanel: () => <p>Market research form</p> }));

import { TradingAiResearchTabs } from './TradingAiResearchTabs';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const binding = { binding_id: 'b1', supported_intervals: ['1h', '4h'] } as unknown as ProviderBinding;
const other = { binding_id: 'b2', supported_intervals: ['1m'] } as unknown as ProviderBinding;

describe('TradingAiResearchTabs', () => {
  it('opens on Copilot, offers only the binding intervals, and switches the active chart when a proposal is applied', async () => {
    const { activeChartId } = useTradingStore.getState();
    useTradingStore.getState().updateChart(activeChartId, { interval: '1h' });
    const copilot = vi.spyOn(tradingResearchApi, 'copilot').mockResolvedValue({
      reply: 'The 4h view shows the trend.', points: [], actions_dropped: 0, headlines: [], news_status: 'not_used',
      actions: [{ id: 'a1', kind: 'set_interval', label: 'Switch to 4h', interval: '4h', indicator: null, period: null, price: null, time: null, start: null, end: null, note: null }],
      facts: { close: '100' }, provider: 'claude', model: 'haiku', read_only: true,
      disclaimer: 'Research only. Not financial advice. No order was created or executed.',
    } as unknown as CopilotResult);
    render(wrap(
      <TradingAiResearchTabs instrumentId="crypto:BTC/USD" bindingId="b1" interval="1h" providerBindings={[other, binding]} indicators={[]} onSetIndicators={vi.fn()} />,
    ));

    expect(screen.getByRole('tab', { name: 'Copilot' }).getAttribute('aria-selected')).toBe('true');
    fireEvent.change(screen.getByLabelText('Ask Copilot'), { target: { value: 'Trend?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    fireEvent.click(await screen.findByRole('button', { name: '+ Switch to 4h' }));
    expect(copilot.mock.calls[0][0].supported_intervals).toEqual(['1h', '4h']);
    expect(useTradingStore.getState().charts.find((chart) => chart.chartId === activeChartId)?.interval).toBe('4h');

    fireEvent.click(screen.getByRole('tab', { name: 'Report' }));
    await waitFor(() => expect(screen.getByText('Market research form')).toBeTruthy());
  });
});
