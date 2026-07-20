import { afterEach, describe, expect, it } from 'vitest';

import {
  ACTIVE_PRONUNCIATIONS_KEY,
} from '../chatbot/livePronunciationClient';
import {
  LIVE_CONVERSATION_EFFECTIVE_PROFILE_KEY,
  type LiveConversationProfile,
} from '../chatbot/liveConversationProfileClient';
import {
  createLiveSpeechSynthesisOptions,
  resetLiveSpeechCueState,
} from './live-speech-synthesis-options';

const profile: LiveConversationProfile = {
  presence_preset: 'natural',
  talkativeness: 50,
  conversation_stance: 'advise',
  conversation_pace: 'reflective',
  interruption_preference: 'balanced',
  assistant_backchannel_mode: 'natural',
  initiative_mode: 'gentle',
  idle_threshold_ms: 15_000,
  long_pause_behavior: 'wait',
  response_length: 'conversational',
  response_onset_style: 'reflective',
  emotional_attunement: 'expressive',
  topic_continuity: 'natural',
  max_idle_prompts: 1,
  duplex_mode: 'echo_aware',
  pronunciation_save_policy: 'ask',
  profile_version: 1,
};

afterEach(() => {
  window.localStorage.clear();
  resetLiveSpeechCueState();
});

describe('explicit live speech synthesis options', () => {
  it('reads the effective profile and pronunciation hints at phrase commit time', () => {
    window.localStorage.setItem(LIVE_CONVERSATION_EFFECTIVE_PROFILE_KEY, JSON.stringify(profile));
    window.localStorage.setItem(ACTIVE_PRONUNCIATIONS_KEY, JSON.stringify([
      {
        id: 'p1',
        phrase: 'Omnix',
        pronunciation: 'Om-nicks',
        locale: 'en-US',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]));

    const options = createLiveSpeechSynthesisOptions('I think Omnix should wait.');

    expect(options.performancePlan).toMatchObject({
      schema_version: 1,
      speech_act: 'instruction',
      pace: 'slightly_slow',
      clause_pause: 'long',
      onset_policy: {
        desired_perceived_onset_ms: 650,
        maximum_additional_delay_ms: 350,
      },
    });
    expect(options.pronunciationLexicon).toEqual([
      { phrase: 'Omnix', pronunciation: 'Om-nicks', locale: 'en-US' },
    ]);
  });

  it('applies calibrated uncertainty without changing the synthesis text contract', () => {
    window.localStorage.setItem(LIVE_CONVERSATION_EFFECTIVE_PROFILE_KEY, JSON.stringify(profile));

    const options = createLiveSpeechSynthesisOptions('My best estimate is that it could finish tomorrow.');

    expect(options.performancePlan).toMatchObject({
      certainty: 'low',
      pace: 'natural',
    });
    expect(options).not.toHaveProperty('text');
  });

  it('returns an empty explicit contract when no profile or pronunciation state is available', () => {
    expect(createLiveSpeechSynthesisOptions('Hello.')).toEqual({});
  });
});
