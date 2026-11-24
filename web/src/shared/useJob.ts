import { useQuery } from '@tanstack/react-query';
import { omnixApiClient } from '../api/client';
import { isJobSettled, jobKeys } from '../api/jobs';

/**
 * One platform job, polled until it settles. A waiting, retrying or paused job has not finished,
 * so polling continues; a completed, failed, canceled or stale one stops it. A lookup that still fails after
 * React Query's retries (the job is gone, or the API is down) stops it too. An empty id is off.
 */
export function useJob(jobId: string | null | undefined, { intervalMs = 1000 }: { intervalMs?: number } = {}) {
  const id = jobId ?? '';
  return useQuery({
    queryKey: jobKeys.detail(id),
    queryFn: () => omnixApiClient.getJob(id),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.status === 'error' || isJobSettled(query.state.data?.status) ? false : intervalMs,
  });
}
