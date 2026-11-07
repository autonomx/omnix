import { afterEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_VOICE_PERF_EVENT } from '../../../events/bus';
import { liveConversationStore } from './live-conversation-store';
import { noteLiveSttNegotiation, resetLiveSttCapabilityState } from './live-stt-capability-state';
import { controller, type LiveVoiceSession } from './live-voice-controller-state';
import { handleProviderEndpointCandidate } from './live-voice-endpointing';
import { semanticFinalizationRemainingMs } from './live-voice-finalization';

// Smart Turn (from the STT service) scores every pause. Ending a turn sooner on a confident score is off since
// 2026-11-06 (it cut people off mid-sentence); the score is still kept and logged, to find a safe setting later.

afterEach(() => {
  controller.activeSession = null;
  liveConversationStore.reset();
  resetLiveSttCapabilityState();
  vi.useRealTimers();
});

function negotiateParakeet(): void {
  noteLiveSttNegotiation('nemotron_parakeet_eou', [
    'segmented_audio', 'authoritative_final', 'result_replay', 'partial_transcripts', 'authoritative_eou',
  ]);
}

function pausedSession(card: HTMLElement, pausedForMs: number): LiveVoiceSession {
  const now = performance.now();
  return {
    card,
    partialTranscript: 'I think we should go tonight',
    partialTranscriptUpdatedAt: now - 300,
    pauseStartedAt: now - pausedForMs,
    speechDetected: true,
    finalRequested: false,
    silenceTimer: setTimeout(() => undefined, 10_000),
    turnComplete: null,
    perfTurnId: 'voice-turn:test',
    sttAuthority: { authorityEnabled: true, endpointThreshold: 0.5 },
    client: { authoritativePreviewSupported: true },
    reporter: { record: vi.fn() },
  } as unknown as LiveVoiceSession;
}

function rescheduledRemainingMs(run: () => void): number | null {
  let remaining: number | null = null;
  const listener = (event: Event) => {
    const detail = (event as CustomEvent<Record<string, unknown>>).detail;
    if (detail.stage === 'semantic_turn_rescheduled') remaining = Number(detail.remainingMs);
  };
  window.addEventListener(ASSISTANT_VOICE_PERF_EVENT, listener);
  try { run(); } finally { window.removeEventListener(ASSISTANT_VOICE_PERF_EVENT, listener); }
  return remaining;
}

describe('Smart Turn end of turn', () => {
  it('keeps the usual wait whatever the score', () => {
    negotiateParakeet();
    expect(semanticFinalizationRemainingMs('I think we should go tonight', 'balanced', 50, 0, 0.97)).toBe(450);
    expect(semanticFinalizationRemainingMs('I think we should go tonight', 'balanced', 50, 0, null)).toBe(450);
  });

  it('records a confident score without bringing the turn-ending timer forward', () => {
    vi.spyOn(console, 'info').mockImplementation(() => undefined);
    negotiateParakeet();
    const card = document.createElement('section');
    const session = pausedSession(card, 50);
    controller.activeSession = session;

    const remaining = rescheduledRemainingMs(() => handleProviderEndpointCandidate(card, {
      segmentId: 'segment-1', sequence: 1, probability: 1, turnComplete: 0.97,
    }));

    expect(session.turnComplete).toBe(0.97);
    expect(remaining).toBeNull();
    expect(session.reporter.record).toHaveBeenCalledWith(
      'stt_endpoint_candidate', expect.objectContaining({ turn_complete: 0.97 }), 'live_voice_controller',
    );
    clearTimeout(session.silenceTimer!);
  });

  it('leaves the timer alone when the voice does not sound finished', () => {
    vi.spyOn(console, 'info').mockImplementation(() => undefined);
    negotiateParakeet();
    const card = document.createElement('section');
    const session = pausedSession(card, 50);
    controller.activeSession = session;

    const remaining = rescheduledRemainingMs(() => handleProviderEndpointCandidate(card, {
      segmentId: 'segment-1', sequence: 1, probability: 1, turnComplete: 0.2,
    }));

    expect(remaining).toBeNull();
    expect(session.turnComplete).toBe(0.2);
    clearTimeout(session.silenceTimer!);
  });
});

describe('Smart Turn verdicts across the tail of the voice', () => {
  it('keeps a verdict heard on the tail of the voice, not one from a pause they talked through', async () => {
    const { turnVerdictAtPause } = await import('./live-voice-finalization');
    expect(turnVerdictAtPause(0.97, 1_000, 1_250)).toBe(0.97);
    expect(turnVerdictAtPause(0.97, 1_000, 1_401)).toBeNull();
    expect(turnVerdictAtPause(null, null, 1_250)).toBeNull();
  });

  it('ignores a verdict on one word, and while the assistant is speaking', () => {
    vi.spyOn(console, 'info').mockImplementation(() => undefined);
    negotiateParakeet();
    const card = document.createElement('section');
    const oneWord = pausedSession(card, 50);
    oneWord.partialTranscript = 'Okay.';
    controller.activeSession = oneWord;

    handleProviderEndpointCandidate(card, { segmentId: 'segment-1', sequence: 1, probability: 1, turnComplete: 0.985 });

    expect(oneWord.turnComplete).toBeNull();
    clearTimeout(oneWord.silenceTimer!);

    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });
    const overHer = pausedSession(card, 50);
    controller.activeSession = overHer;
    handleProviderEndpointCandidate(card, { segmentId: 'segment-1', sequence: 2, probability: 1, turnComplete: 0.878 });
    expect(overHer.turnComplete).toBeNull();
    clearTimeout(overHer.silenceTimer!);
  });
});
