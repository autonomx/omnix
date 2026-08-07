import { describe, expect, it, vi } from 'vitest';

import {
  earlySpeculationCandidateEligible,
  earlySpeculationProbabilityFloor,
  initializeLiveSpeculationEarlyTrigger,
} from './live-speculation-early-trigger';
import {
  LIVE_STT_SPECULATION_CANDIDATE_EVENT,
  LIVE_STT_SPECULATION_PARTIAL_EVENT,
} from './live-stt-authority-controller';

describe('early live speculation trigger', () => {
  it('starts longer stable candidates at a lower bounded endpoint score', () => {
    expect(earlySpeculationProbabilityFloor('What kind of nonsense is this')).toBe(0.35);
    expect(earlySpeculationCandidateEligible(
      0.35,
      'What kind of nonsense is this',
    )).toBe(true);
  });

  it('requires more confidence for two-word candidates', () => {
    expect(earlySpeculationProbabilityFloor('Stop now')).toBe(0.6);
    expect(earlySpeculationCandidateEligible(0.59, 'Stop now')).toBe(false);
    expect(earlySpeculationCandidateEligible(0.6, 'Stop now')).toBe(true);
  });

  it('allows only guarded one-word complete utterances at very high confidence', () => {
    expect(earlySpeculationProbabilityFloor('Why?')).toBe(0.9);
    expect(earlySpeculationCandidateEligible(0.89, 'Why?')).toBe(false);
    expect(earlySpeculationCandidateEligible(0.9, 'Why?')).toBe(true);
    expect(earlySpeculationProbabilityFloor('because')).toBeNull();
    expect(earlySpeculationCandidateEligible(0.99, 'because')).toBe(false);
  });

  it('does not speculate below the bounded long-candidate probability floor', () => {
    expect(earlySpeculationCandidateEligible(
      0.34,
      'What kind of nonsense is this',
    )).toBe(false);
  });

  it('uses the exact STT partial for the scored segment instead of waiting for store mirroring', () => {
    const candidateListener = vi.fn();
    const perfListener = vi.fn();
    window.addEventListener(LIVE_STT_SPECULATION_CANDIDATE_EVENT, candidateListener);
    window.addEventListener('omnix:assistant-voice-perf', perfListener);
    const cleanup = initializeLiveSpeculationEarlyTrigger();

    try {
      window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
        detail: {
          stage: 'stt_authority_selected',
          authorityEnabled: true,
          selectedProvider: 'kyutai',
        },
      }));
      window.dispatchEvent(new CustomEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, {
        detail: {
          chatSessionId: 'chat:early',
          segmentId: 'segment-early',
          sourceSequence: 7,
          text: 'What kind of nonsense is this',
        },
      }));
      window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
        detail: {
          stage: 'stt_endpoint_score',
          provider: 'kyutai',
          segmentId: 'segment-early',
          sourceSequence: 7,
          probability: 0.35,
          modelTimeMs: 1200,
        },
      }));

      expect(candidateListener).toHaveBeenCalledOnce();
      expect((candidateListener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
        chatSessionId: 'chat:early',
        segmentId: 'segment-early',
        sourceSequence: 7,
        text: 'What kind of nonsense is this',
        probability: 0.35,
        earlyTrigger: true,
      });
      expect(perfListener).toHaveBeenCalledWith(expect.objectContaining({
        detail: expect.objectContaining({
          stage: 'llm_speculation_early_candidate_dispatched',
          transcriptChars: 29,
          transcriptWords: 6,
        }),
      }));
    } finally {
      cleanup();
      window.removeEventListener(LIVE_STT_SPECULATION_CANDIDATE_EVENT, candidateListener);
      window.removeEventListener('omnix:assistant-voice-perf', perfListener);
    }
  });
});
