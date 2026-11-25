import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradingFilingsPanel } from './TradingFilingsPanel';
import type { FilingEntry, FilingSummaryResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const filing: FilingEntry = {
  accession: '0000320193-26-000101', form: '8-K', filed: '2026-10-30', report_date: '2026-10-30', description: 'Results of operations',
  items: ['2.02', '9.01'], url: 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000101/aapl-8k.htm', document: 'aapl-8k.htm',
};

const summary: FilingSummaryResult = {
  filing, company: 'Apple Inc.', title: 'Q4 results', summary: 'Revenue rose on services.', highlights: ['Services at a record.'],
  risks: ['Tariffs.'], figures: [{ label: 'Revenue', value: '$102.5 billion' }], figures_dropped: 1,
  documents: [{ name: 'aapl-8k.htm', url: filing.url }, { name: 'aapl-ex991.htm', url: 'https://www.sec.gov/x' }],
  characters_read: 36000, characters_total: 90000, provider: 'claude', model: 'haiku', read_only: true,
  disclaimer: 'Research only. Not financial advice. No order was created or executed.',
};

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('TradingFilingsPanel', () => {
  it('lists the company reports and summarizes the one chosen', async () => {
    vi.spyOn(tradingResearchApi, 'filings').mockResolvedValue({ instrument_id: 'equity:NASDAQ:AAPL', ticker: 'AAPL', company: 'Apple Inc.', cik: '0000320193', filings: [filing] });
    const summarize = vi.spyOn(tradingResearchApi, 'filingSummary').mockResolvedValue(summary);
    render(wrap(<TradingFilingsPanel instrumentId="equity:NASDAQ:AAPL" />));

    expect(await screen.findByText('Results of operations')).toBeTruthy();
    expect(screen.getByText('Apple Inc. · SEC EDGAR')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'SEC' }).getAttribute('href')).toBe(filing.url);
    fireEvent.click(screen.getByRole('button', { name: 'Summarize 8-K filed 2026-10-30' }));

    expect(await screen.findByText('Q4 results')).toBeTruthy();
    expect(summarize).toHaveBeenCalledWith('equity:NASDAQ:AAPL', filing.accession);
    expect(screen.getByText('$102.5 billion')).toBeTruthy();
    expect(screen.getByText(/aapl-8k\.htm, aapl-ex991\.htm \(an excerpt: 36,000 of 90,000 characters\)/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Close summary' }));
    await waitFor(() => expect(screen.queryByText('Q4 results')).toBeNull());
  });

  it('asks nothing for a non-stock and shows a missing SEC contact as the error', async () => {
    const filings = vi.spyOn(tradingResearchApi, 'filings');
    render(wrap(<TradingFilingsPanel instrumentId="crypto:BTC/USD" />));
    expect(screen.getByText('Filing summaries are for US stocks.')).toBeTruthy();
    expect(filings).not.toHaveBeenCalled();
    cleanup();

    filings.mockRejectedValue(new Error('Filings request failed (409): Set an SEC contact email in Settings.'));
    render(wrap(<TradingFilingsPanel instrumentId="equity:NASDAQ:AAPL" />));
    expect((await screen.findByRole('alert')).textContent).toContain('SEC contact');
  });
});
