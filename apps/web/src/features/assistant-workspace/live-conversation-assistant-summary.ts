export const LIVE_ASSISTANT_TURN_SUMMARY_EVENT = 'omnix:live-conversation-assistant-summary';

export type LiveAssistantTurnSummary = {
  turnId: string | null;
  turnKind: 'greeting' | 'response';
  wordCount: number;
  questionCount: number;
  topicFingerprint: string | null;
  createsObligation: boolean;
};

const OBLIGATION_PATTERN = /(?:\?|\b(?:would you like|do you want|can you|could you|will you|should we|shall we|tell me|let me know)\b)/i;
const STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'for', 'from', 'had', 'has', 'have',
  'he', 'her', 'his', 'i', 'if', 'in', 'is', 'it', 'its', 'me', 'my', 'of', 'on', 'or', 'our',
  'she', 'so', 'that', 'the', 'their', 'them', 'there', 'they', 'this', 'to', 'was', 'we', 'were',
  'what', 'when', 'where', 'which', 'who', 'why', 'will', 'with', 'would', 'you', 'your',
]);

export function summarizeAssistantTurn(
  text: string,
  turnId: string | null,
  turnKind: 'greeting' | 'response',
): LiveAssistantTurnSummary {
  const normalized = text.replace(/\s+/g, ' ').trim();
  const words = normalized.match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu) ?? [];
  const questions = normalized.match(/[?？]+/g) ?? [];
  return {
    turnId,
    turnKind,
    wordCount: words.length,
    questionCount: questions.length,
    topicFingerprint: fingerprintTopic(words),
    createsObligation: turnKind === 'response' && OBLIGATION_PATTERN.test(normalized),
  };
}

export function dispatchAssistantTurnSummary(summary: LiveAssistantTurnSummary): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LIVE_ASSISTANT_TURN_SUMMARY_EVENT, { detail: summary }));
}

function fingerprintTopic(words: string[]): string | null {
  const significant = words
    .map((word) => word.toLocaleLowerCase().replace(/[’']/g, ''))
    .filter((word) => word.length >= 3 && !STOP_WORDS.has(word))
    .slice(0, 24)
    .sort();
  if (significant.length < 2) return null;
  let hash = 2166136261;
  for (const character of significant.join('|')) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `topic-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
