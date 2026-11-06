import './live-voice-backchannel';
import './live-voice-conversation-settings';

import {
  type InterruptionPreference,
  readLiveConversationSettings,
} from './live-voice-conversation-settings';
import { isPlaybackEchoSuppressed } from './live-voice-echo-suppression';

export type OverlapIntent = 'hard_stop' | 'interrupt' | 'backchannel' | 'noise' | 'uncertain';

export type OverlapAssessment = {
  intent: OverlapIntent;
  confidence: number;
  reason: string;
};

const HARD_STOP_PATTERN = /^(?:stop|wait|hold on|cancel|pause|quiet|be quiet|no|nope|that's wrong|that is wrong)[.!?\s-]*$/i;
const CORRECTION_PATTERN = /\b(?:no|not|wrong|actually|correction|I meant|you said|that's not|that is not)\b/i;
const QUESTION_OPENING_PATTERN = /^(?:what|why|when|where|who|how|can|could|would|should|did|do|does|is|are)\b/i;
const NON_SPEECH_PATTERN = /^(?:\[?(?:noise|cough|breath|music|silence|background)\]?|[.!,…\s-]*)$/i;

/**
 * What can be settled at once from the words alone, because it has to act at once: an explicit stop, a correction, a
 * question, or a remark too long to be a reaction. People react in any words, so nothing here tries to list them:
 * what remains is `uncertain`, and the call's model judges it once its final transcript is in
 * (`live-voice-overlap-judge.ts`, `live-voice-final-routing.ts`).
 */
export function classifyOverlap(
  transcript: string,
  assistantText = '',
): OverlapAssessment {
  const text = normalize(transcript);
  if (!text) return { intent: 'uncertain', confidence: 0.1, reason: 'no_stable_text' };
  if (NON_SPEECH_PATTERN.test(text)) return { intent: 'noise', confidence: 0.96, reason: 'non_speech_marker' };
  if (isLikelyEcho(text, assistantText)) return { intent: 'noise', confidence: 0.9, reason: 'assistant_echo' };
  if (HARD_STOP_PATTERN.test(text)) return { intent: 'hard_stop', confidence: 0.99, reason: 'explicit_stop' };
  if (CORRECTION_PATTERN.test(text)) return { intent: 'interrupt', confidence: 0.9, reason: 'correction' };
  const words = text.split(/\s+/).filter(Boolean);
  // One word is not yet a question: it may be a first partial, or a reaction such as "Really?".
  if (words.length >= 2 && QUESTION_OPENING_PATTERN.test(text)) return { intent: 'interrupt', confidence: 0.86, reason: 'question' };
  if (words.length >= 4 || text.length >= 24) {
    return { intent: 'interrupt', confidence: 0.74, reason: 'sustained_overlap' };
  }
  return { intent: 'uncertain', confidence: 0.45, reason: 'short_ambiguous_overlap' };
}

export function isLikelyEcho(transcript: string, assistantText: string): boolean {
  const inputWords = wordSet(transcript);
  const outputWords = wordSet(assistantText);
  if (inputWords.size < 3 || outputWords.size < 3) return false;
  let overlap = 0;
  for (const word of inputWords) if (outputWords.has(word)) overlap += 1;
  return overlap / inputWords.size >= 0.78;
}

export function shouldConfirmInterruption(
  assessment: OverlapAssessment,
  preference: InterruptionPreference = readLiveConversationSettings().interruptionPreference,
): boolean {
  // Acoustic echo has stronger evidence than a partial STT overlap transcript.
  // A subsequent independent-speech acoustic verdict clears this latch before
  // the user's real transcript reaches the semantic classifier.
  if (isPlaybackEchoSuppressed()) return false;
  if (assessment.intent === 'hard_stop') return true;
  if (assessment.intent !== 'interrupt') return false;
  const threshold = preference === 'easy' ? 0.58 : preference === 'finish_more' ? 0.86 : 0.7;
  return assessment.confidence >= threshold;
}

function normalize(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

function wordSet(value: string): Set<string> {
  return new Set(
    normalize(value)
      .toLocaleLowerCase()
      .replace(/[^\p{L}\p{N}'\s]/gu, ' ')
      .split(/\s+/)
      .filter((word) => word.length > 1),
  );
}
