import type { SpeechPerformancePlan } from './live-speech-performance-contract';
import { cueVariantId, type LiveVoiceCueId } from './live-voice-cue-bank';

// A reply's sound plays only where the model wrote a tag ([hmm], [chuckle], [sigh]); guessing one from the words
// is gone. This decides whether the tag may play here.
const RESPONSE_CUE_COOLDOWN_MS = 12_000;
const SENSITIVE_PATTERN = /\b(?:password|passcode|pin|account|card number|security code|address|phone number|email address|diagnosis|emergency)\b|\b\d{4,}\b/i;

export type ResponseCueDecision = {
  allowed: boolean;
  cueId: LiveVoiceCueId | null;
  variantId: string | null;
  reason: string;
};

export function decideResponseCue(
  tagCue: LiveVoiceCueId | null | undefined,
  text: string,
  plan: SpeechPerformancePlan | undefined,
  sequence: number,
  now = Date.now(),
  lastCueAt = 0,
): ResponseCueDecision {
  if (!tagCue) return denied('no_tag');
  if (!plan) return denied('no_performance_plan');
  // Emotional attunement "off" turns every nonverbal sound off (server: live_conversation_rendering.py).
  if (!plan.nonverbal_eligibility.breath) return denied('attunement_off');
  if (SENSITIVE_PATTERN.test(text)) return denied('sensitive_content');
  if (now - lastCueAt < RESPONSE_CUE_COOLDOWN_MS) return denied('cooldown');
  return {
    allowed: true,
    cueId: tagCue,
    variantId: cueVariantId(tagCue, sequence),
    reason: `tag_${tagCue}`,
  };
}

export function mapBackchannelTokenToCue(token: string): LiveVoiceCueId {
  return token.trim().toLocaleLowerCase() === 'mhm' ? 'mhm' : 'hmm';
}

function denied(reason: string): ResponseCueDecision {
  return { allowed: false, cueId: null, variantId: null, reason };
}
