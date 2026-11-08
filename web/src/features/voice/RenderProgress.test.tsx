import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { JobRecord } from '../../api/client';
import { RenderProgress } from './RenderProgress';

function job(status: string, progress: { current: number; total: number; message?: string }): JobRecord {
  return {
    id: 'job:render', module: 'voice', type: 'tts.multi_speaker_synthesize', status, resource_class: 'gpu:tts',
    priority: 0, progress, created_at: '2026-11-07T00:00:00Z', updated_at: '2026-11-07T00:00:00Z',
  } as unknown as JobRecord;
}

function percent(): number {
  return Number(screen.getByRole('progressbar', { name: 'Speech generation progress' }).getAttribute('aria-valuenow'));
}

describe('RenderProgress', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('waits at 0% until the engine takes the job', () => {
    render(<RenderProgress job={job('queued', { current: 0, total: 1 })} estimatedSeconds={7} />);
    expect(screen.getByText('Waiting for the speech engine…')).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(5000); });
    expect(percent()).toBe(0);
  });

  it('moves within a line but never claims the next one, then follows the reported lines', () => {
    const { rerender } = render(<RenderProgress job={job('running', { current: 0, total: 3, message: 'Line 1 of 2 (Narrator)' })} estimatedSeconds={8} />);
    expect(screen.getByText('Line 1 of 2 (Narrator)…')).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(2000); });
    const early = percent();
    expect(early).toBeGreaterThan(0);
    act(() => { vi.advanceTimersByTime(60_000); });
    // A third of the work is the first line; the bar stops short of it until the job says so.
    expect(percent()).toBeGreaterThan(early);
    expect(percent()).toBeLessThan(33);

    rerender(<RenderProgress job={job('running', { current: 2, total: 3, message: 'Assembling the take' })} estimatedSeconds={8} />);
    expect(screen.getByText('Assembling the take…')).toBeInTheDocument();
    expect(percent()).toBeGreaterThanOrEqual(66);
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(percent()).toBeLessThan(100);

    rerender(<RenderProgress job={job('completed', { current: 3, total: 3 })} estimatedSeconds={8} />);
    expect(percent()).toBe(100);
  });
});
