import { readEffectiveLiveConversationProfile } from '../chatbot/liveConversationProfileClient';
import { readActivePronunciations } from '../chatbot/livePronunciationClient';
import { createSpeechDeliveryPlan } from './live-speech-delivery-plan';
import type {
  SpeechPerformancePlan,
  SpeechSynthesisOptions,
} from './live-speech-performance-contract';
import { decideResponseCue, type ResponseCueDecision } from './live-voice-cue-policy';
import {
  humanizeSpeechPerformance,
  resetVocalInteractionState,
} from './live-voice-performance-behavior';

const CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const CALL_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';

export type LiveSpeechSynthesisPlanningOptions = {
  scopeKey?: string;
  enablePerformancePlan?: boolean;
  enableVocalContinuity?: boolean;
};

let responseCueSequence = 0;
let lastResponseCueAt = 0;
let resetListenersInstalled = false;

export function createLiveSpeechSynthesisOptions(
  text: string,
  options: LiveSpeechSynthesisPlanningOptions = {},
): SpeechSynthesisOptions {
  installResetListeners();
  const profile = readEffectiveLiveConversationProfile();
  const performanceEnabled = options.enablePerformancePlan ?? true;
  const continuityEnabled = options.enableVocalContinuity ?? true;
  const serious = /\b(?:sorry|grief|loss|afraid|hurt|serious|take your time)\b/i.test(text);
  const basePerformancePlan = profile && performanceEnabled
    ? createSpeechDeliveryPlan(text, profile, serious)
    : undefined;
  const performancePlan = basePerformancePlan && profile && continuityEnabled
    ? humanizeSpeechPerformance(
      text,
      basePerformancePlan,
      profile,
      options.scopeKey ?? 'default',
    ).plan
    : basePerformancePlan;
  const pronunciationLexicon = readActivePronunciations().map((entry) => ({
    phrase: entry.phrase,
    pronunciation: entry.pronunciation,
    locale: entry.locale,
  }));
  return {
    ...(performancePlan ? { performancePlan } : {}),
    ...(pronunciationLexicon.length ? { pronunciationLexicon } : {}),
  };
}

export function selectLiveResponseCue(
  text: string,
  plan: SpeechPerformancePlan | undefined,
  phraseIndex: number,
  now = Date.now(),
): ResponseCueDecision {
  installResetListeners();
  const decision = decideResponseCue(
    text,
    plan,
    phraseIndex,
    responseCueSequence,
    now,
    lastResponseCueAt,
  );
  if (decision.allowed) {
    responseCueSequence += 1;
    lastResponseCueAt = now;
  }
  return decision;
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
  window.addEventListener(SESSION_CHANGED_EVENT, resetLiveSpeechCueState);
}
