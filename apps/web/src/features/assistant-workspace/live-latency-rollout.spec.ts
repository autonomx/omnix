import { describe, expect, it, vi } from 'vitest';
import { resolveAuthoritySelection } from './live-stt-authority-controller';
import {
  resolveLiveVoiceSttSelection,
  shouldCommitProviderEndpoint,
} from './live-voice-controller';
import {
  transcriptIsSpeculationSafe,
  transcriptsCanReuseSpeculation,
} from './live-speculation-controller';
import { AdaptiveTtsBufferPolicy } from './live-tts-adaptive-buffer-controller';
import { StableClauseAccumulator } from './live-voice-clause-stabilizer';

const locationLike = { protocol: 'http:', hostname: 'localhost' } as Pick<Location, 'protocol' | 'hostname'>;

describe('live latency PR3-PR5 rollout policies', () => {
  it('selects authoritative Kyutai only after the pre-session gate passes', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      eligible: true,
      reasons: [],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })) as unknown as typeof fetch;

    const selected = await resolveAuthoritySelection(
      'http://127.0.0.1:5202?language=en&authority=test&endpoint_threshold=0.82',
      locationLike,
      fetchImpl,
    );
    expect(selected.authorityEnabled).toBe(true);
    expect(selected.fallbackUsed).toBe(false);
    expect(selected.endpointThreshold).toBe(0.82);
    expect(selected.websocketUrl).toBe('ws://127.0.0.1:5202/ws/transcribe?language=en');
  });

  it('falls back before capture when production authority gates fail', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      ok: false,
      eligible: false,
      reasons: ['quality_gate_not_passed'],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })) as unknown as typeof fetch;

    const selected = await resolveAuthoritySelection(
      'http://127.0.0.1:5202?language=en&authority=auto&fallback=http%3A%2F%2F127.0.0.1%3A5201',
      locationLike,
      fetchImpl,
    );
    expect(selected.authorityEnabled).toBe(false);
    expect(selected.fallbackUsed).toBe(true);
    expect(selected.websocketUrl).toBe('ws://127.0.0.1:5201/ws/transcribe');
    expect(selected.reasons).toContain('quality_gate_not_passed');
  });

  it('uses the controller authority resolver before capture and defaults to Parakeet', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch;
    const selected = await resolveLiveVoiceSttSelection(undefined, locationLike, fetchImpl);

    expect(selected.authorityEnabled).toBe(false);
    expect(selected.fallbackUsed).toBe(false);
    expect(selected.reasons).toEqual(['default_parakeet']);
    expect(selected.websocketUrl).toBe('ws://127.0.0.1:5201/ws/transcribe');
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('allows provider endpoint commitment only through the controller pause state', () => {
    const ready = {
      authorityEnabled: true,
      probability: 0.86,
      endpointThreshold: 0.75,
      speechDetected: true,
      finalRequested: false,
      pausePending: true,
    };
    expect(shouldCommitProviderEndpoint(ready)).toBe(true);
    expect(shouldCommitProviderEndpoint({ ...ready, authorityEnabled: false })).toBe(false);
    expect(shouldCommitProviderEndpoint({ ...ready, probability: 0.7 })).toBe(false);
    expect(shouldCommitProviderEndpoint({ ...ready, pausePending: false })).toBe(false);
    expect(shouldCommitProviderEndpoint({ ...ready, finalRequested: true })).toBe(false);
  });

  it('reuses speculation only when normalized words are unchanged', () => {
    expect(transcriptsCanReuseSpeculation('Tell me a story', 'tell me a story!')).toBe(true);
    expect(transcriptsCanReuseSpeculation('Tell me a story', 'Tell me the story')).toBe(false);
    expect(transcriptIsSpeculationSafe('Wait, no I mean tell me a story')).toBe(false);
  });

  it('commits streamed LLM text to TTS after the low-latency deadline', () => {
    const clauses = new StableClauseAccumulator();
    expect(clauses.append('This response starts early', 1_000)).toEqual([]);
    expect(clauses.takeReady(1_141)).toEqual([
      { text: 'This response starts', reason: 'deadline' },
    ]);
    expect(clauses.pendingText()).toBe('early');
  });

  it('raises buffering after underruns and cautiously lowers it after stable turns', () => {
    const policy = new AdaptiveTtsBufferPolicy({ startBufferMs: 260, rebufferMs: 520 });
    const raised = policy.observeWorkletEvent('underrun');
    expect(raised.startBufferMs).toBeGreaterThan(260);
    expect(raised.rebufferMs).toBeGreaterThan(520);
    policy.observeWorkletEvent('drained');

    const beforeStable = policy.snapshot();
    policy.observeWorkletEvent('drained');
    policy.observeWorkletEvent('drained');
    const lowered = policy.observeWorkletEvent('drained');
    expect(lowered.startBufferMs).toBeLessThan(beforeStable.startBufferMs);
    expect(lowered.rebufferMs).toBeLessThan(beforeStable.rebufferMs);
  });
});
