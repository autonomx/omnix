import {
  readEffectiveLiveConversationProfile,
  type AssistantBackchannelMode,
} from '../chatbot/liveConversationProfileClient';

const PERF_EVENT = 'omnix:assistant-voice-perf';
const USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';
const USER_CONTINUER_EVENT = 'omnix:live-conversation-user-continuer';
const DUCK_EVENT = 'omnix:assistant-audio-duck';
const MIN_COOLDOWN_MS = 8_000;
const MIN_SPEECH_MS = 3_500;
const SENSITIVE_PATTERN = /\b(?:password|passcode|pin|account|card number|security code|address|phone number|email address)\b|\b\d{4,}\b/i;
const QUESTION_OR_CORRECTION_PATTERN = /[?？]|\b(?:no|not|wrong|actually|correction|I meant|did you say)\b/i;
const CONTINUER_PATTERN = /^(?:m+h+m+|mhm+|uh[ -]?huh|yeah|yep|right|okay|ok|got it|sure|I see|mm+)[.!\s-]*$/i;

export type BackchannelToken = 'mhm' | 'right' | 'okay' | "i'm with you";
export type AssistantBackchannelDecision = { allowed: boolean; token: BackchannelToken | null; reason: string };

let initialized = false;
let selectedSessionId: string | null = null;
let lastPlayedAt = 0;
let naturalIndex = 0;
let speechTimer: ReturnType<typeof setTimeout> | null = null;
let restoreTimer: ReturnType<typeof setTimeout> | null = null;

export function isUserContinuer(transcript: string): boolean {
  return CONTINUER_PATTERN.test(transcript.trim());
}

export function decideAssistantListenerBackchannel(
  transcript: string,
  mode: AssistantBackchannelMode,
  speechDurationMs: number,
  now = Date.now(),
  lastAt = lastPlayedAt,
  duplexMode: string = readEffectiveLiveConversationProfile()?.duplex_mode ?? 'automatic',
): AssistantBackchannelDecision {
  const text = transcript.trim();
  if (mode === 'off') return denied('disabled');
  if (duplexMode !== 'echo_aware') return denied('requires_echo_aware_duplex');
  if (speechDurationMs < MIN_SPEECH_MS) return denied('speech_too_short');
  if (now - lastAt < MIN_COOLDOWN_MS) return denied('cooldown');
  if (!text) return denied('no_partial_transcript');
  if (SENSITIVE_PATTERN.test(text)) return denied('sensitive_dictation');
  if (QUESTION_OR_CORRECTION_PATTERN.test(text)) return denied('semantic_risk');
  if (!/[,.!;:]\s*$/.test(text) && text.split(/\s+/).length < 12) return denied('no_safe_clause_boundary');
  if (mode === 'minimal') return { allowed: true, token: 'mhm', reason: 'minimal' };
  const tokens: BackchannelToken[] = ['mhm', 'right', 'okay', "i'm with you"];
  return { allowed: true, token: tokens[naturalIndex % tokens.length], reason: 'natural' };
}

export function resolveBackchannelTranscript(detailTranscript: unknown): string {
  if (typeof detailTranscript === 'string' && detailTranscript.trim()) return detailTranscript.trim();
  const draft = document.querySelector<HTMLElement>('.assistant-live-draft p');
  if (draft?.textContent?.trim()) return draft.textContent.trim();
  const row = document.querySelector<HTMLElement>('.assistant-voice-transcript [data-live-voice-id="live-voice-draft"]');
  if (!row) return '';
  const clone = row.cloneNode(true) as HTMLElement;
  clone.querySelector('span')?.remove();
  return clone.textContent?.trim() ?? '';
}

export function initializeEphemeralBackchannels(): () => void {
  if (initialized || typeof window === 'undefined') return () => undefined;
  initialized = true;

  const handleSession = (event: Event) => {
    const detail = (event as CustomEvent<{ sessionId?: unknown }>).detail;
    if (typeof detail?.sessionId === 'string') selectedSessionId = detail.sessionId;
  };
  const handlePerf = (event: Event) => {
    const detail = (event as CustomEvent<{ stage?: unknown; intent?: unknown; transcript?: unknown }>).detail;
    if (detail?.stage !== 'overlap_classified' || detail.intent !== 'backchannel') return;
    window.dispatchEvent(new CustomEvent(USER_CONTINUER_EVENT, {
      detail: { transcript: resolveBackchannelTranscript(detail.transcript), action: 'continue' },
    }));
  };
  const handleUserSpeech = () => {
    clearSpeechTimer();
    const startedAt = performance.now();
    speechTimer = setTimeout(() => {
      const profile = readEffectiveLiveConversationProfile();
      const decision = decideAssistantListenerBackchannel(
        resolveBackchannelTranscript(undefined),
        profile?.assistant_backchannel_mode ?? 'off',
        performance.now() - startedAt,
        Date.now(),
        lastPlayedAt,
        profile?.duplex_mode ?? 'automatic',
      );
      if (decision.allowed && decision.token && selectedSessionId && !assistantIsSpeaking()) {
        void playCharacterBackchannel(selectedSessionId, decision.token);
      }
    }, MIN_SPEECH_MS);
  };
  const cancel = () => { clearSpeechTimer(); restoreOutput('cancelled'); };

  window.addEventListener(SESSION_CHANGED_EVENT, handleSession);
  window.addEventListener(PERF_EVENT, handlePerf);
  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(INTERRUPT_EVENT, cancel);
  window.addEventListener(STOP_EVENT, cancel);

  return () => {
    window.removeEventListener(SESSION_CHANGED_EVENT, handleSession);
    window.removeEventListener(PERF_EVENT, handlePerf);
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(INTERRUPT_EVENT, cancel);
    window.removeEventListener(STOP_EVENT, cancel);
    cancel();
    initialized = false;
  };
}

async function playCharacterBackchannel(sessionId: string, token: BackchannelToken): Promise<void> {
  lastPlayedAt = Date.now();
  naturalIndex += 1;
  window.dispatchEvent(new CustomEvent(DUCK_EVENT, { detail: { gain: 0.35, reason: 'listener-backchannel' } }));
  const params = new URLSearchParams({
    purpose: 'proactive_reengagement',
    initiative_reason: `listener_backchannel:${token}`,
  });
  try {
    await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/live-call/greeting/stream?${params}`, { method: 'POST' });
  } finally {
    if (restoreTimer) clearTimeout(restoreTimer);
    restoreTimer = setTimeout(() => restoreOutput('listener-backchannel-complete'), 1_800);
  }
}

function assistantIsSpeaking(): boolean {
  return Array.from(document.querySelectorAll<HTMLElement>('.assistant-voice-orb')).some((orb) => orb.dataset.voiceMode === 'speaking');
}

function clearSpeechTimer(): void {
  if (speechTimer) clearTimeout(speechTimer);
  speechTimer = null;
}

function restoreOutput(reason: string): void {
  if (restoreTimer) clearTimeout(restoreTimer);
  restoreTimer = null;
  window.dispatchEvent(new CustomEvent(DUCK_EVENT, { detail: { gain: 1, reason } }));
}

function denied(reason: string): AssistantBackchannelDecision {
  return { allowed: false, token: null, reason };
}

if (typeof window !== 'undefined') initializeEphemeralBackchannels();
