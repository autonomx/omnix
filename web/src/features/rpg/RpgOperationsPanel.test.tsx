import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../test/renderWithProviders';
import { RpgOperationsPanel } from './RpgOperationsPanel';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgOperationsPanel', () => {
  it("shows each day's turns, failures, degraded stages and the slowest turn class", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async () => new Response(JSON.stringify({
      ok: true,
      days: [{
        day: '2026-10-25', turns: 40, failed: 1, degraded: 2, failure_rate: 0.025, degraded_rate: 0.05,
        model_calls: 30, model_failures: 0, model_calls_per_turn: 0.75,
        classes: [
          { turn_class: 'look', turns: 20, p50_ms: 210, p95_ms: 320 },
          { turn_class: 'travel', turns: 20, p50_ms: 260, p95_ms: 410 },
        ],
      }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    render(<QueryClientProvider client={createTestQueryClient()}><RpgOperationsPanel days={7} /></QueryClientProvider>);

    expect(await screen.findByRole('rowheader', { name: '2026-10-25' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '1 (2.5%)' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '2 (5.0%)' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'travel: 410 ms' })).toBeInTheDocument();
    expect(screen.getByText(/look 20× p50 210 ms/)).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/rpg/operations?days=7');
  });

  it('says so when no turn is recorded yet', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: true, days: [] }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })));
    render(<QueryClientProvider client={createTestQueryClient()}><RpgOperationsPanel /></QueryClientProvider>);
    expect(await screen.findByText('No turns recorded yet.')).toBeInTheDocument();
  });
});
