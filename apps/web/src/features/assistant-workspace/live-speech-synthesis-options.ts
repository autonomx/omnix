import { readEffectiveLiveConversationProfile } from '../chatbot/liveConversationProfileClient';
import { readActivePronunciations } from '../chatbot/livePronunciationClient';
import { createSpeechDeliveryPlan } from './live-speech-delivery-plan';
import type { SpeechSynthesisOptions } from './live-speech-performance-contract';
import { decideResponseCue } from './live-voice-cue-policy';
import { playLowLatencyVoiceCue } from './live-voice-cue-player';

let responseCueSequence = 0;
let lastResponseCueAt = 0;

export function createLiveSpeechSynthesisOptions(text: string): SpeechSynthesisOptions {
  const profile = readEffectiveLiveConversationProfile();
  const serious = /\b(?:sorry|grief|loss|afraid|hurt|serious|take your time)\b/i.test(text);
  const performancePlan = profile ? createSpeechDeliveryPlan(text, profile, serious) : undefined;
  const pronunciationLexicon = readActivePronunciations().map((entry) => ({
    phrase: entry.phrase,
    pronunciation: entry.pronunciation,
    locale: entry.locale,
  }));
  const now = Date.now();
  const cue = decideResponseCue(
    text,
    performancePlan,
    0,
    responseCueSequence,
    now,
    lastResponseCueAt,
  );
  if (cue.allowed && cue.cueId && cue.variantId) {
    responseCueSequence += 1;
    lastResponseCueAt = now;
    void playLowLatencyVoiceCue(cue.cueId, cue.variantId, 0.62);
  }
  return {
    ...(performancePlan ? { performancePlan } : {}),
    ...(pronunciationLexicon.length ? { pronunciationLexicon } : {}),
  };
}

export function resetLiveSpeechCueState(): void {
  responseCueSequence = 0;
  lastResponseCueAt = 0;
}
