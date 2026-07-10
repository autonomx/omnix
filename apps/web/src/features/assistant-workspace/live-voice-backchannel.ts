import {
  type BackchannelMode,
  readLiveConversationSettings,
} from './live-voice-conversation-settings';

const PERF_EVENT = 'omnix:assistant-voice-perf';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const BACKCHANNEL_EVENT = 'omnix:assistant-backchannel';
const MIN_COOLDOWN_MS = 6_000;
const SENSITIVE_PATTERN = /\b(?:password|passcode|pin|account|card number|security code|address|phone number|email address)\b|\b\d{4,}\b/i;
const QUESTION_OR_CORRECTION_PATTERN = /[?？]|\b(?:no|not|wrong|actually|correction|I meant)\b/i;

export type BackchannelToken = 'mhm' | 'right' | 'okay' | 'listening';

export type BackchannelDecision = {
  allowed: boolean;
  token: BackchannelToken | null;
  reason: string;
};

type VoicePerfDetail = {
  stage?: unknown;
  intent?: unknown;
  reason?: unknown;
  transcript?: unknown;
};

type BackchannelDetail = {
  token: BackchannelToken;
  expiresAfterMs: number;
};

let initialized = false;
let lastPlayedAt = 0;
let naturalIndex = 0;

export function decideBackchannel(
  transcript: string,
  mode: BackchannelMode,
  now = Date.now(),
  lastAt = lastPlayedAt,
): BackchannelDecision {
  const text = transcript.trim();
  if (mode === 'off') return { allowed: false, token: null, reason: 'disabled' };
  if (now - lastAt < MIN_COOLDOWN_MS) return { allowed: false, token: null, reason: 'cooldown' };
  if (SENSITIVE_PATTERN.test(text)) return { allowed: false, token: null, reason: 'sensitive_dictation' };
  if (QUESTION_OR_CORRECTION_PATTERN.test(text)) return { allowed: false, token: null, reason: 'semantic_turn' };
  if (text && !/^(?:m+h+m+|mhm+|uh[ -]?huh|yeah|yep|right|okay|ok|got it|sure|I see|mm+)[.!\s-]*$/i.test(text)) {
    return { allowed: false, token: null, reason: 'not_acknowledgement' };
  }
  if (mode === 'minimal') return { allowed: true, token: 'mhm', reason: 'minimal' };
  const tokens: BackchannelToken[] = ['mhm', 'right', 'okay', 'listening'];
  return { allowed: true, token: tokens[naturalIndex % tokens.length], reason: 'natural' };
}

export function requestEphemeralBackchannel(
  transcript = '',
  mode = readLiveConversationSettings().backchannelMode,
): boolean {
  const now = Date.now();
  const decision = decideBackchannel(transcript, mode, now, lastPlayedAt);
  if (!decision.allowed || !decision.token) return false;
  lastPlayedAt = now;
  naturalIndex += 1;
  window.dispatchEvent(new CustomEvent<BackchannelDetail>(BACKCHANNEL_EVENT, {
    detail: { token: decision.token, expiresAfterMs: 900 },
  }));
  return true;
}

export function cancelEphemeralBackchannel(): void {
  if (typeof window === 'undefined') return;
  window.speechSynthesis?.cancel();
}

export function resolveBackchannelTranscript(detailTranscript: unknown): string {
  if (typeof detailTranscript === 'string' && detailTranscript.trim()) return detailTranscript.trim();
  const draft = document.querySelector<HTMLElement>(
    '.assistant-voice-transcript [data-live-voice-id="live-voice-draft"]',
  );
  if (!draft) return '';
  const clone = draft.cloneNode(true) as HTMLElement;
  clone.querySelector('span')?.remove();
  return clone.textContent?.trim() ?? '';
}

export function initializeEphemeralBackchannels(): void {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;
  window.addEventListener(PERF_EVENT, handleVoicePerfEvent);
  window.addEventListener(BACKCHANNEL_EVENT, handleBackchannelEvent as EventListener);
  window.addEventListener(INTERRUPT_EVENT, cancelEphemeralBackchannel);
  window.addEventListener(STOP_EVENT, cancelEphemeralBackchannel);
}

function handleVoicePerfEvent(event: Event): void {
  const detail = (event as CustomEvent<VoicePerfDetail>).detail;
  if (detail?.stage !== 'overlap_classified' || detail.intent !== 'backchannel') return;
  requestEphemeralBackchannel(resolveBackchannelTranscript(detail.transcript));
}

function handleBackchannelEvent(event: CustomEvent<BackchannelDetail>): void {
  const detail = event.detail;
  if (!detail?.token || typeof SpeechSynthesisUtterance === 'undefined' || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(detail.token);
  utterance.volume = 0.35;
  utterance.rate = detail.token === 'listening' ? 1.12 : 1.04;
  utterance.pitch = 1;
  const configuredVoice = configuredVoiceName();
  if (configuredVoice) {
    const voice = window.speechSynthesis.getVoices().find((candidate) =>
      candidate.name.toLocaleLowerCase().includes(configuredVoice.toLocaleLowerCase()),
    );
    if (voice) utterance.voice = voice;
  }
  window.speechSynthesis.speak(utterance);
  window.setTimeout(() => {
    if (window.speechSynthesis.speaking) window.speechSynthesis.cancel();
  }, Math.max(250, detail.expiresAfterMs));
}

function configuredVoiceName(): string | null {
  try {
    const parsed = JSON.parse(window.localStorage.getItem('omnix.chatbot.assistantSettings') || '{}') as { voiceId?: unknown };
    return typeof parsed.voiceId === 'string' && parsed.voiceId.trim() ? parsed.voiceId.trim() : null;
  } catch {
    return null;
  }
}

initializeEphemeralBackchannels();
