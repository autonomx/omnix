import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradingNewsDigest } from './TradingNewsDigest';
import type { NewsDigestResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const digest: NewsDigestResult = {
  symbol: 'NVDA', window: '7d', start: '2026-11-17T00:00:00Z', end: '2026-11-24T00:00:00Z', news_status: 'ok',
  title: 'Earnings week', summary: 'Results beat; export rules weigh.', tone: 'mixed',
  themes: [{ title: 'Earnings', summary: 'Revenue beat estimates.', headlines: [{ id: 'h1', headline: 'Nvidia beats', source: 'benzinga', url: 'https://news.example/1', created_at: '2026-11-20T21:00:00Z' }] }],
  headlines_considered: 12, provider: 'claude', model: 'haiku', read_only: true,
  disclaimer: 'Research only. Not financial advice. No order was created or executed.',
};

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('TradingNewsDigest', () => {
  it('summarizes the chosen window into themes with their headlines', async () => {
    const run = vi.spyOn(tradingResearchApi, 'newsDigest').mockResolvedValue(digest);
    render(wrap(<TradingNewsDigest instrumentId="equity:NASDAQ:NVDA" />));
    fireEvent.change(screen.getByLabelText('Digest window'), { target: { value: '7d' } });
    fireEvent.click(screen.getByRole('button', { name: 'Summarize headlines' }));

    expect(await screen.findByText('Earnings week')).toBeTruthy();
    expect(run.mock.calls[0][0]).toEqual({ instrument_id: 'equity:NASDAQ:NVDA', window: '7d' });
    expect(screen.getByText('mixed').getAttribute('data-tone')).toBe('mixed');
    expect(screen.getByRole('region', { name: 'Earnings' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Nvidia beats' })).toBeTruthy();
    expect(screen.getByText('12 headlines · haiku')).toBeTruthy();
  });

  it('says so when there is no news, without a digest', async () => {
    vi.spyOn(tradingResearchApi, 'newsDigest').mockResolvedValue({
      ...digest, news_status: 'none', title: '', tone: null, themes: [], headlines_considered: 0, provider: null, model: null,
      summary: 'No headlines tagged NVDA in the last 3 days.',
    });
    render(wrap(<TradingNewsDigest instrumentId="equity:NASDAQ:NVDA" />));
    fireEvent.click(screen.getByRole('button', { name: 'Summarize headlines' }));
    expect(await screen.findByText('No headlines tagged NVDA in the last 3 days.')).toBeTruthy();
    expect(screen.queryByRole('article')).toBeNull();
  });
});
