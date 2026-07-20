import { readEffectiveLiveConversationProfile } from '../chatbot/liveConversationProfileClient';
import { readActivePronunciations } from '../chatbot/livePronunciationClient';
import { createSpeechDeliveryPlan } from './live-speech-delivery-plan';
import type { SpeechSynthesisOptions } from './live-speech-performance-contract';

export function createLiveSpeechSynthesisOptions(text: string): SpeechSynthesisOptions {
  const profile = readEffectiveLiveConversationProfile();
  const serious = /\b(?:sorry|grief|loss|afraid|hurt|serious|take your time)\b/i.test(text);
  const performancePlan = profile ? createSpeechDeliveryPlan(text, profile, serious) : undefined;
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
