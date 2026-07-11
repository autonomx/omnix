import type { LiveConversationProfile } from '../chatbot/liveConversationProfileClient';

export type SpeechDeliveryPlan = {
  speech_act: 'acknowledgement' | 'answer' | 'question' | 'reassurance' | 'reflection' | 'instruction';
  energy: 'low' | 'moderate' | 'high';
  warmth: 'low' | 'moderate' | 'high';
  certainty: 'low' | 'moderate' | 'high';
  pace: 'slightly_slow' | 'natural' | 'slightly_fast';
  clause_pause: 'short' | 'medium' | 'long';
  emphasis: string[];
};

export function createSpeechDeliveryPlan(
  text: string,
  profile: LiveConversationProfile,
  serious = false,
): SpeechDeliveryPlan {
  const normalized = text.trim();
  const lower = normalized.toLocaleLowerCase();
  let speechAct: SpeechDeliveryPlan['speech_act'] = normalized.endsWith('?') ? 'question' : 'answer';
  if (/\b(?:i understand|that sounds|take your time|i'm sorry|i am sorry)\b/.test(lower)) speechAct = 'reassurance';
  else if (profile.conversation_stance === 'listen') speechAct = 'reflection';
  else if (profile.conversation_stance === 'teach' || profile.conversation_stance === 'advise') speechAct = 'instruction';
  else if (normalized.split(/\s+/).filter(Boolean).length <= 4) speechAct = 'acknowledgement';

  return {
    speech_act: speechAct,
    energy: serious || speechAct === 'reassurance' || speechAct === 'reflection' ? 'low' : profile.presence_preset === 'engaged' ? 'high' : 'moderate',
    warmth: serious || profile.emotional_attunement === 'expressive' ? 'high' : profile.emotional_attunement === 'off' ? 'low' : 'moderate',
    certainty: /\b(?:maybe|perhaps|might|not sure|uncertain)\b/.test(lower) ? 'low' : speechAct === 'answer' || speechAct === 'instruction' ? 'high' : 'moderate',
    pace: serious || profile.response_length === 'detailed' ? 'slightly_slow' : profile.conversation_pace === 'quick' ? 'slightly_fast' : 'natural',
    clause_pause: serious ? 'long' : speechAct === 'acknowledgement' ? 'short' : 'medium',
    emphasis: normalized.split(/\s+/).map((word) => word.replace(/[.,!?;:]/g, '')).filter((word) => word.length > 1 && word === word.toLocaleUpperCase()).slice(0, 6),
  };
}

export function applyDeliveryPlanToTtsRequest(
  payload: Record<string, unknown>,
  plan: SpeechDeliveryPlan,
): Record<string, unknown> {
  const temperature = typeof payload.temperature === 'number' ? payload.temperature : 0.6;
  const topP = typeof payload.top_p === 'number' ? payload.top_p : 0.85;
  const temperatureDelta = plan.energy === 'high' ? 0.05 : plan.energy === 'low' ? -0.04 : 0;
  const warmthDelta = plan.warmth === 'high' ? 0.02 : plan.warmth === 'low' ? -0.01 : 0;
  return {
    ...payload,
    temperature: clamp(temperature + temperatureDelta + warmthDelta, 0.45, 0.8),
    top_p: clamp(topP + (plan.energy === 'high' ? 0.03 : plan.energy === 'low' ? -0.02 : 0), 0.75, 0.95),
    repetition_penalty: Math.max(typeof payload.repetition_penalty === 'number' ? payload.repetition_penalty : 1, 1.05),
    delivery_plan: plan,
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, Number(value.toFixed(3))));
}
