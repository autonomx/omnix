import { afterEach, describe, expect, it } from 'vitest';

import {
  currentLiveSttCapabilities,
  liveSttUsesFinalOnlyEndpointing,
  resetLiveSttCapabilityState,
} from './live-stt-capability-state';

afterEach(() => {
  resetLiveSttCapabilityState();
});

describe('live STT capability state', () => {
  it('learns the negotiated provider capabilities from live voice perf events', () => {
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'parakeet',
        capabilities: ['segmented_audio', 'authoritative_final', 'result_replay'],
      },
    }));

    expect(currentLiveSttCapabilities()).toEqual({
      provider: 'parakeet',
      capabilities: ['authoritative_final', 'result_replay', 'segmented_audio'],
      negotiated: true,
    });
    expect(liveSttUsesFinalOnlyEndpointing()).toBe(true);
  });

  it('does not classify semantic or unknown capability sets as final-only', () => {
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'kyutai',
        capabilities: [
          'segmented_audio',
          'authoritative_final',
          'continuous_words',
          'semantic_endpointing',
        ],
      },
    }));
    expect(liveSttUsesFinalOnlyEndpointing()).toBe(false);

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'future-provider',
        capabilities: ['segmented_audio', 'authoritative_final', 'partial_transcripts'],
      },
    }));
    expect(liveSttUsesFinalOnlyEndpointing()).toBe(false);
  });

  it('ignores unrelated performance events', () => {
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_final_received',
        provider: 'parakeet',
        capabilities: ['segmented_audio', 'authoritative_final', 'result_replay'],
      },
    }));

    expect(currentLiveSttCapabilities()).toEqual({
      provider: null,
      capabilities: [],
      negotiated: false,
    });
    expect(liveSttUsesFinalOnlyEndpointing()).toBe(false);
  });
});
