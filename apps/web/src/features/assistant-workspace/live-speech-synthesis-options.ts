import { readEffectiveLiveConversationProfile } from '../chatbot/liveConversationProfileClient';
import { readActivePronunciations } from '../chatbot/livePronunciationClient';
import { createSpeechDeliveryPlan } from './live-speech-delivery-plan';
import type { SpeechSynthesisOptions } from './live-speech-performance-contract';
import { decideResponseCue } from './live-voice-cue-policy';
import { playLowLatencyVoiceCue } from './live-voice-cue-player';
import {
  humanizeSpeechPerformance,
  resetVocalInteractionState,
} from './live-voice-performance-behavior';

const CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const CALL_STOP_EVENT = 'omnix:assistant-live-voice-stop';

let responseCueSequence = 0;
let lastResponseCueAt = 0;
let resetListenersInstalled = false;

export function createLiveSpeechSynthesisOptions(text: string): SpeechSynthesisOptions {
  installResetListeners();
  const profile = readEffectiveLiveConversationProfile();
  const serious = /\b(?:sorry|grief|loss|afraid|hurt|serious|take your time)\b/i.test(text);
  const basePerformancePlan = profile ? createSpeechDeliveryPlan(text, profile, serious) : undefined;
  const performancePlan = basePerformancePlan && profile
    ? humanizeSpeechPerformance(text, basePerformancePlan, profile).plan
    : undefined;
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
  resetVocalInteractionState();
}

function installResetListeners(): void {
  if (resetListenersInstalled || typeof window === 'undefined') return;
  resetListenersInstalled = true;
  window.addEventListener(CALL_START_EVENT, resetLiveSpeechCueState);
  window.addEventListener(CALL_STOP_EVENT, resetLiveSpeechCueState);
}
