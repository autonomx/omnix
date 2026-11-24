import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixApiClient, type JobRecord } from '../api/client';
import { jobKeys } from '../api/jobs';
import { useJob } from './useJob';

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function job(status: string): JobRecord {
  return { id: 'job-1', status } as unknown as JobRecord;
}

describe('useJob', () => {
  afterEach(() => vi.restoreAllMocks());

  it('polls a job until it settles, then stops', async () => {
    const statuses = ['queued', 'retrying', 'completed'];
    const getJob = vi.spyOn(omnixApiClient, 'getJob').mockImplementation(async () => job(statuses.shift() ?? 'completed'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useJob('job-1', { intervalMs: 10 }), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.data?.status).toBe('completed'));
    const calls = getJob.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(getJob.mock.calls.length).toBe(calls);
    expect(client.getQueryData(jobKeys.detail('job-1'))).toMatchObject({ status: 'completed' });
  });

  it('stops polling when the job cannot be read', async () => {
    const getJob = vi.spyOn(omnixApiClient, 'getJob').mockRejectedValue(new Error('404'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useJob('job-1', { intervalMs: 10 }), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const calls = getJob.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(getJob.mock.calls.length).toBe(calls);
  });

  it('does not fetch without a job id', () => {
    const getJob = vi.spyOn(omnixApiClient, 'getJob');
    const client = new QueryClient();
    renderHook(() => useJob(null), { wrapper: wrapper(client) });
    renderHook(() => useJob(''), { wrapper: wrapper(client) });
    expect(getJob).not.toHaveBeenCalled();
  });

  it('keeps a single job under the jobs prefix, apart from the lists', () => {
    expect(jobKeys.detail('pages').slice(0, 2)).toEqual([...jobKeys.all]);
    expect(jobKeys.detail('pages')).not.toEqual([...jobKeys.all, 'pages']);
  });
});
