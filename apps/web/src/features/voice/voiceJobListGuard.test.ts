import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type GuardWindow = Window & typeof globalThis & {
  __omnixVoiceJobListGuardInstalled?: boolean;
};

beforeEach(() => {
  vi.resetModules();
  delete (window as GuardWindow).__omnixVoiceJobListGuardInstalled;
  window.history.replaceState({}, '', '/voice');
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
  delete (window as GuardWindow).__omnixVoiceJobListGuardInstalled;
});

describe('Voice Studio bounded job list guard', () => {
  it('uses the bounded summary endpoint on the Voice Studio route', async () => {
    const responsePayload = { jobs: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(responsePayload), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const { omnixApiClient } = await import('../../api/client');
    const originalListJobs = vi.spyOn(omnixApiClient, 'listJobs').mockResolvedValue({ jobs: [] });

    await import('./voiceJobListGuard');
    const result = await omnixApiClient.listJobs();

    expect(result).toEqual(responsePayload);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/jobs/voice-summaries?limit=40',
      { headers: { Accept: 'application/json' } },
    );
    expect(originalListJobs).not.toHaveBeenCalled();
  });

  it('leaves non-Voice routes on the normal jobs API', async () => {
    window.history.replaceState({}, '', '/jobs');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const { omnixApiClient } = await import('../../api/client');
    const expected = { jobs: [] };
    const originalListJobs = vi.spyOn(omnixApiClient, 'listJobs').mockResolvedValue(expected);

    await import('./voiceJobListGuard');
    const result = await omnixApiClient.listJobs();

    expect(result).toBe(expected);
    expect(originalListJobs).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('suppresses unbounded history when the bounded endpoint fails', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('unavailable', { status: 503 }));
    vi.stubGlobal('fetch', fetchMock);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { omnixApiClient } = await import('../../api/client');
    const originalListJobs = vi.spyOn(omnixApiClient, 'listJobs').mockResolvedValue({ jobs: [] });

    await import('./voiceJobListGuard');
    const result = await omnixApiClient.listJobs();

    expect(result).toEqual({ jobs: [] });
    expect(originalListJobs).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalled();
  });
});
