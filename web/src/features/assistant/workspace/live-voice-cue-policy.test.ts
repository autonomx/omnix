import { describe, expect, it } from 'vitest';

import type { SpeechPerformancePlan } from './live-speech-performance-contract';
import { decideResponseCue, mapBackchannelTokenToCue } from './live-voice-cue-policy';

const plan: SpeechPerformancePlan = {
  schema_version: 1,
  speech_act: 'reflection',
  energy: 'low',
  warmth: 'high',
  certainty: 'moderate',
  pace: 'slightly_slow',
  clause_pause: 'long',
  emphasis: [],
  onset_policy: {
    desired_perceived_onset_ms: 650,
    maximum_additional_delay_ms: 350,
  },
  nonverbal_eligibility: {
    breath: true,
    acknowledgement: true,
    amused_exhale: true,
    sigh: false,
  },
};

describe('live voice cue policy', () => {
  it('plays the sound the model tagged, on any clause', () => {
    expect(decideResponseCue('hmm', 'The safer option is to wait.', plan, 0, 20_000, 0)).toEqual({
      allowed: true,
      cueId: 'hmm',
      variantId: 'hmm-v1',
      reason: 'tag_hmm',
    });
    expect(decideResponseCue('amused_exhale', 'That worked.', plan, 1, 20_000, 0).variantId)
      .toBe('amused_exhale-v2');
    expect(decideResponseCue('sigh', 'Long day.', plan, 0, 20_000, 0).cueId).toBe('sigh');
  });

  it('never guesses a sound from the words', () => {
    expect(decideResponseCue(null, "I think that's funny.", plan, 0, 20_000, 0)).toEqual({
      allowed: false,
      cueId: null,
      variantId: null,
      reason: 'no_tag',
    });
  });

  it('stays silent with attunement off, without a plan, on sensitive content and inside the cooldown', () => {
    const off = { ...plan, nonverbal_eligibility: { ...plan.nonverbal_eligibility, breath: false } };
    expect(decideResponseCue('hmm', 'Maybe.', off, 0, 20_000, 0).reason).toBe('attunement_off');
    expect(decideResponseCue('hmm', 'Maybe.', undefined, 0, 20_000, 0).reason).toBe('no_performance_plan');
    expect(decideResponseCue('hmm', 'Your passcode is 123456.', plan, 0, 20_000, 0).reason)
      .toBe('sensitive_content');
    expect(decideResponseCue('hmm', 'This is right.', plan, 0, 20_000, 15_000).reason).toBe('cooldown');
  });

  it('maps listener tokens onto the bounded cue set', () => {
    expect(mapBackchannelTokenToCue('mhm')).toBe('mhm');
    expect(mapBackchannelTokenToCue('right')).toBe('hmm');
    expect(mapBackchannelTokenToCue("i'm with you")).toBe('hmm');
  });
});
