import { beforeEach, describe, expect, it } from 'vitest';

import type { LiveConversationProfile } from '../chatbot/liveConversationProfileClient';
import { ACTIVE_PRONUNCIATIONS_KEY } from '../chatbot/livePronunciationClient';
import { enrichLiveTtsFrame } from './live-speech-delivery-bridge';

const profile: LiveConversationProfile = {
  presence_preset: 'natural', talkativeness: 50, conversation_stance: 'discuss', conversation_pace: 'balanced',
  interruption_preference: 'balanced', assistant_backchannel_mode: 'off', initiative_mode: 'gentle',
  idle_threshold_ms: 15000, long_pause_behavior: 'wait', response_length: 'conversational',
  response_onset_style: 'adaptive', emotional_attunement: 'subtle', topic_continuity: 'natural',
  max_idle_prompts: 1, duplex_mode: 'automatic', pronunciation_save_policy: 'ask', profile_version: 1,
};

beforeEach(() => {
  window.localStorage.clear();
});

describe('enrichLiveTtsFrame', () => {
  it('adds delivery and active pronunciation metadata only to synthesize frames', () => {
    window.localStorage.setItem(ACTIVE_PRONUNCIATIONS_KEY, JSON.stringify([
      { id: 'one', phrase: 'Nika', pronunciation: 'NEE-kah', locale: 'en-US', created_at: '', updated_at: '' },
    ]));
    const result = enrichLiveTtsFrame({
      type: 'synthesize', text: 'Hello Nika.', temperature: 0.6, top_p: 0.85,
    }, profile);

    expect(result.plan?.speech_act).toBe('acknowledgement');
    expect(result.frame.delivery_plan).toEqual(result.plan);
    expect(result.frame.pronunciation_lexicon).toEqual([
      { phrase: 'Nika', pronunciation: 'NEE-kah', locale: 'en-US' },
    ]);
  });

  it('leaves non-synthesis frames unchanged', () => {
    const frame = { type: 'diagnostic', event: 'ready' };
    expect(enrichLiveTtsFrame(frame, profile)).toEqual({ frame, plan: null });
  });
});
