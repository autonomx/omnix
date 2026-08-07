import { describe, expect, it, vi } from 'vitest';

import {
  initializeLiveSpeculationRuntime,
  liveSubmissionRequestMatches,
} from './live-speculation-runtime';

const submission = {
  sessionId: 'chat:one',
  text: 'Hello',
  source: 'live_coordination' as const,
  interrupted: false,
  segmentId: 'segment-1',
  sourceSequence: 1,
};

describe('live speculation runtime routing', () => {
  it('matches only the active live submission chat stream', () => {
    expect(liveSubmissionRequestMatches(
      submission,
      '/api/chat/sessions/chat%3Aone/messages/stream',
      { method: 'POST' },
    )).toBe(true);
    expect(liveSubmissionRequestMatches(
      submission,
      '/api/chat/sessions/chat%3Atwo/messages/stream',
      { method: 'POST' },
    )).toBe(false);
    expect(liveSubmissionRequestMatches(
      submission,
      '/api/chat/sessions/chat%3Aone/messages/stream',
      { method: 'GET' },
    )).toBe(false);
  });

  it('keeps speculation inside a later live-audio fetch wrapper', async () => {
    const priorFetch = window.fetch;
    const order: string[] = [];
    const applicationFetch = vi.fn(async () => {
      order.push('application');
      return new Response('ok', { status: 200 });
    });
    window.fetch = applicationFetch as typeof window.fetch;

    const cleanup = initializeLiveSpeculationRuntime();
    const speculationFetch = window.fetch.bind(window);
    expect(window.fetch).not.toBe(applicationFetch);

    window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      order.push('audio');
      return speculationFetch(input, init);
    }) as typeof window.fetch;

    try {
      const response = await window.fetch(
        '/api/chat/sessions/chat%3Aone/messages/stream',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: 'Hello' }),
        },
      );
      expect(await response.text()).toBe('ok');
      expect(order).toEqual(['audio', 'application']);
      expect(applicationFetch).toHaveBeenCalledOnce();
    } finally {
      cleanup();
      window.fetch = priorFetch;
    }
  });
});
