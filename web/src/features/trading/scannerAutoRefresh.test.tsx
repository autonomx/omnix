import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ definitions: vi.fn(), runs: vi.fn(), results: vi.fn(), start: vi.fn(), create: vi.fn(), cancel: vi.fn() }));
vi.mock('./tradingScannerApi', () => ({ tradingScannerApi: api }));

import { resultChanges, useScannerAutoRefresh } from './scannerAutoRefresh';
import type { TradingScannerResult } from './scannerTypes';
import { TradingScannerPanel } from './TradingScannerPanel';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

const result = (instrumentId: string, runId = 'run-1') => ({ run_id: runId, instrument_id: instrumentId, rank: 1, provider: 'p', score: '1', dataset_fingerprint: 'abcdef1234' }) as unknown as TradingScannerResult;

describe('screener auto-refresh (TVP-9.2)', () => {
  it('says what changed since the previous run', () => {
    expect(resultChanges(null, [result('a')])).toEqual({ added: new Set(), removed: [] });
    const changes = resultChanges([result('a'), result('b')], [result('b'), result('c')]);
    expect([...changes.added]).toEqual(['c']);
    expect(changes.removed).toEqual(['a']);
  });

  it('starts a run on its cadence, never while one is still working', () => {
    vi.useFakeTimers();
    let busy = false;
    const start = vi.fn(async () => undefined);
    const hook = renderHook(() => useScannerAutoRefresh({ scannerId: 's', everyMs: 10_000 }, () => busy, start));
    act(() => { vi.advanceTimersByTime(10_000); });
    expect(start).toHaveBeenCalledTimes(1);
    busy = true;
    act(() => { vi.advanceTimersByTime(10_000); });
    expect(start).toHaveBeenCalledTimes(1);
    hook.unmount();
    busy = false;
    act(() => { vi.advanceTimersByTime(30_000); });
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('turns auto-refresh on from a saved screen and highlights new results', async () => {
    api.definitions.mockResolvedValue([{ scanner_id: 's1', name: 'Movers', instrument_ids: ['a'], interval: '1d', revision: 1 }]);
    api.runs.mockResolvedValue([{ run_id: 'run-1', scanner_id: 's1', status: 'completed', completed_count: 2, universe_count: 2, matched_count: 2 }]);
    api.results.mockResolvedValueOnce([result('a'), result('b')]);
    api.start.mockResolvedValue({});
    render(<TradingScannerPanel instruments={[]} />);
    const auto = await screen.findByLabelText('Auto-refresh Movers');
    api.runs.mockResolvedValue([{ run_id: 'run-2', scanner_id: 's1', status: 'completed', completed_count: 2, universe_count: 2, matched_count: 2 }]);
    api.results.mockResolvedValueOnce([result('b', 'run-2'), result('c', 'run-2')]);
    fireEvent.change(auto, { target: { value: '10000' } });
    await waitFor(() => expect(api.start).toHaveBeenCalledWith('s1'));
    expect(await screen.findByRole('status')).toHaveTextContent('1 new, 1 dropped (a)');
    expect(screen.getByText('c').closest('tr')).toHaveClass('is-new');
  });
});
