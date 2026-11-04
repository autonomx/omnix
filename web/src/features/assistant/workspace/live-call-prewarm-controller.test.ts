import { afterEach, describe, expect, it, vi } from 'vitest';

import { initializeLiveCallPrewarmController, prewarmLiveCall } from './live-call-prewarm-controller';
import { ASSISTANT_VOICE_PERF_EVENT } from '../../../events/bus';


function callIdOf(input: RequestInfo | URL, init?: RequestInit): string | null {
  return new Headers(input instanceof Request ? input.headers : init?.headers).get('X-Omnix-Call-Id');
}

describe('live call prewarm controller', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not cache a partial warm-up and retries after the cooldown', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-06T00:00:00Z'));
    const stages: string[] = [];
    const recordStage = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail;
      if (typeof detail?.stage === 'string') stages.push(detail.stage);
    };
    window.addEventListener(ASSISTANT_VOICE_PERF_EVENT, recordStage);

    let prewarmCalls = 0;
    const replicaCalls: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      if (url.includes('/live-call/runtime')) {
        return new Response(JSON.stringify({ voice_speaker_id: 'Jinx' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/prewarm')) {
        const callId = callIdOf(input, init);
        if (callId) {
          replicaCalls.push(callId);
          return Response.json({ ok: true, fully_warmed: true, status: 'completed', cached: false });
        }
        prewarmCalls += 1;
        const fullyWarmed = prewarmCalls > 1;
        return new Response(JSON.stringify({
          ok: fullyWarmed,
          fully_warmed: fullyWarmed,
          status: fullyWarmed ? 'completed' : 'partial',
          cached: false,
          llm: { status: fullyWarmed ? 'warmed' : 'failed' },
          tts: { status: 'warmed' },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    try {
      await prewarmLiveCall('session-partial', fetchImpl);
      await prewarmLiveCall('session-partial', fetchImpl);
      expect(prewarmCalls).toBe(1);
      expect(stages).toContain('live_call_prewarm_partial');
      // Reaches the call's replica too, whose turns take their own waiting process.
      expect(replicaCalls).toEqual(['session-partial']);

      vi.advanceTimersByTime(5_001);
      await prewarmLiveCall('session-partial', fetchImpl);
      expect(prewarmCalls).toBe(2);
      expect(stages).toContain('live_call_prewarm_completed');
    } finally {
      window.removeEventListener(ASSISTANT_VOICE_PERF_EVENT, recordStage);
    }
  });

  it('still warms the worker when the replica cannot be reached', async () => {
    let worker = 0;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().includes('/live-call/runtime')) return Response.json({ voice_speaker_id: 'Jinx' });
      if (callIdOf(input, init)) throw new TypeError('network');
      worker += 1;
      return Response.json({ ok: true, fully_warmed: true, status: 'completed', cached: false });
    }) as unknown as typeof fetch;

    await prewarmLiveCall('session-no-replica', fetchImpl);

    expect(worker).toBe(1);
  });

  it('warms a chat again when it switches identity, however recently it was warmed', async () => {
    let worker = 0;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().includes('/live-call/runtime')) return Response.json({ voice_speaker_id: 'Jinx' });
      if (!callIdOf(input, init)) worker += 1;
      return Response.json({ ok: true, fully_warmed: true, status: 'completed', cached: false });
    }) as unknown as typeof fetch;
    const identity = (detail: Record<string, unknown>) => window.dispatchEvent(
      new CustomEvent('omnix:character-avatar-runtime', { detail }),
    );
    const dispose = initializeLiveCallPrewarmController();
    try {
      identity({ interaction_mode: 'character', character_id: 'jinx', character_profile_version: 6 });
      await prewarmLiveCall('session-identity', fetchImpl);
      await prewarmLiveCall('session-identity', fetchImpl);
      expect(worker).toBe(1); // warmed recently, same identity

      identity({ interaction_mode: 'system', character_id: null, character_profile_version: null });
      await prewarmLiveCall('session-identity', fetchImpl);
      expect(worker).toBe(2); // its prompt is another one now

      window.dispatchEvent(new CustomEvent('omnix:character-avatar-runtime', { detail: null })); // no runtime: not a switch
      await prewarmLiveCall('session-identity', fetchImpl);
      expect(worker).toBe(2);
    } finally {
      dispose();
    }
  });
});