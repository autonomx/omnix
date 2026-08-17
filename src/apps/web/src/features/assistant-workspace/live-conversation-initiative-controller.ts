import {
  LIVE_CONVERSATION_PROFILE_CHANGED_EVENT,
  readEffectiveLiveConversationProfile,
  type LiveConversationProfile,
} from '../chatbot/liveConversationProfileClient';
import type { PresencePolicyValues } from './live-chat-evaluation-client';
import { decideInitiative } from './live-conversation-initiative-policy';
import { liveConversationStore } from './live-conversation-store';

const SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';
const CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const CALL_CONNECTED_EVENT = 'omnix:assistant-live-voice-call-connected';
const USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const PERF_EVENT = 'omnix:assistant-voice-perf';
const DELIVERED_EVENT = 'omnix:live-conversation-proactive-delivered';
const SCHEDULER_INTERVAL_MS = 750;
const DEFAULT_COOLDOWN_MS = 30_000;
const AUDIO_START_TIMEOUT_MS = 5_000;
const THINKING_PATTERN = /\b(?:give me (?:a )?(?:second|minute|moment)|let me think|one moment|hold on|I need a minute)\b/i;
const SENSITIVE_PATTERN = /\b(?:password|passcode|pin|account|card number|security code|address|phone number|email address)\b|\b\d{4,}\b/i;

type InitiativeWindow = Window & typeof globalThis & {
  __omnixLiveConversationInitiativeInstalled?: boolean;
};

type PendingProactive = {
  sessionId: string;
  turnId: string;
  content: string;
  reason: string;
  audioStarted: boolean;
  committing: boolean;
};

export type ParsedProactiveStream = {
  turnId: string;
  content: string;
  initiativeReason: string;
};

export type InitiativePolicyTiming = {
  idleThresholdMs: number;
  cooldownMs: number;
  typicalTurnWords: number | null;
  responseOnsetMs: number | null;
};

let selectedSessionId: string | null = null;
let callConnected = false;
let lastActivityAtMs = 0;
let lastPromptAtMs: number | null = null;
let promptCount = 0;
let previousPromptIgnored = false;
let requestController: AbortController | null = null;
let pending: PendingProactive | null = null;
let assistantSpeaking = false;
let audioStartTimer: ReturnType<typeof setTimeout> | null = null;

export function initializeLiveConversationInitiativeController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const liveWindow = window as InitiativeWindow;
  if (liveWindow.__omnixLiveConversationInitiativeInstalled) return () => undefined;
  liveWindow.__omnixLiveConversationInitiativeInstalled = true;
  lastActivityAtMs = performance.now();
  selectedSessionId = liveConversationStore.getState().sessionId;
  callConnected = liveConversationStore.getState().conversation.connection === 'connected';
  assistantSpeaking = isAssistantSpeaking();

  const handleSession = (event: Event) => {
    const detail = (event as CustomEvent<{ sessionId?: unknown }>).detail;
    selectedSessionId = typeof detail?.sessionId === 'string' ? detail.sessionId : selectedSessionId;
    resetQuietPeriod('session-changed');
  };
  const handleCallStart = () => { callConnected = false; resetQuietPeriod('call-started'); };
  const handleCallConnected = () => { callConnected = true; resetQuietPeriod('call-connected'); };
  const handleUserSpeech = () => {
    const hadPlayingPrompt = Boolean(pending?.audioStarted);
    requestController?.abort('user-speech');
    requestController = null;
    if (hadPlayingPrompt) previousPromptIgnored = true;
    else clearPending('user-spoke-before-playback');
    lastActivityAtMs = performance.now();
    promptCount = 0;
  };
  const handleInterrupt = () => {
    if (pending?.audioStarted) void commitPending('interrupted');
    else clearPending('interrupted-before-playback');
    lastActivityAtMs = performance.now();
  };
  const handleStop = () => {
    callConnected = false;
    requestController?.abort('call-stopped');
    requestController = null;
    resetQuietPeriod('call-stopped');
  };
  const handleProfile = () => resetQuietPeriod('profile-changed');

  window.addEventListener(SESSION_CHANGED_EVENT, handleSession);
  window.addEventListener(CALL_START_EVENT, handleCallStart);
  window.addEventListener(CALL_CONNECTED_EVENT, handleCallConnected);
  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(INTERRUPT_EVENT, handleInterrupt);
  window.addEventListener(STOP_EVENT, handleStop);
  window.addEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);

  const unsubscribe = liveConversationStore.subscribe(handleAuthoritativeStateChange);
  handleAuthoritativeStateChange();
  const scheduler = window.setInterval(evaluateInitiative, SCHEDULER_INTERVAL_MS);

  return () => {
    window.clearInterval(scheduler);
    unsubscribe();
    window.removeEventListener(SESSION_CHANGED_EVENT, handleSession);
    window.removeEventListener(CALL_START_EVENT, handleCallStart);
    window.removeEventListener(CALL_CONNECTED_EVENT, handleCallConnected);
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(INTERRUPT_EVENT, handleInterrupt);
    window.removeEventListener(STOP_EVENT, handleStop);
    window.removeEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);
    requestController?.abort('controller-disposed');
    requestController = null;
    clearPending('controller-disposed');
    liveWindow.__omnixLiveConversationInitiativeInstalled = false;
  };
}

export function parseProactiveSse(text: string): ParsedProactiveStream | null {
  let turnId = '';
  let content = '';
  let initiativeReason = '';
  for (const block of text.split(/\n\n+/)) {
    const data = block.split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) continue;
    let event: Record<string, unknown>;
    try { event = JSON.parse(data) as Record<string, unknown>; } catch { continue; }
    if (event.type === 'error') throw new Error(String(event.message || 'Proactive turn failed.'));
    if (event.type === 'initiative') {
      if (typeof event.turn_id === 'string') turnId = event.turn_id;
      if (typeof event.initiative_reason === 'string') initiativeReason = event.initiative_reason;
    }
    if (event.type === 'complete') {
      if (typeof event.content === 'string') content = event.content.trim();
      const metadata = event.metadata as Record<string, unknown> | undefined;
      if (!turnId && typeof metadata?.turn_id === 'string') turnId = metadata.turn_id;
      if (!initiativeReason && typeof metadata?.initiative_reason === 'string') initiativeReason = metadata.initiative_reason;
    }
  }
  return turnId && content ? { turnId, content, initiativeReason: initiativeReason || 'continue_current_topic' } : null;
}

export function proactiveReasonFromTranscript(transcript?: string): string | null {
  const latest = (transcript ?? currentDraftOrTranscript()).trim();
  if (!latest) return null;
  return /\?\s*$/.test(latest) ? 'unresolved_question' : 'continue_current_topic';
}

export function resolveInitiativePolicyTiming(
  profileIdleThresholdMs: number,
  policy: PresencePolicyValues | null,
): InitiativePolicyTiming {
  if (!policy) {
    return {
      idleThresholdMs: profileIdleThresholdMs,
      cooldownMs: DEFAULT_COOLDOWN_MS,
      typicalTurnWords: null,
      responseOnsetMs: null,
    };
  }
  return {
    // The explicit Live Chat profile/session setting owns when the first idle
    // prompt is eligible. Presence policy still tunes cooldown, length, and
    // response onset, but must not silently lengthen the configured delay.
    idleThresholdMs: profileIdleThresholdMs,
    cooldownMs: policy.initiative_cooldown_ms,
    typicalTurnWords: policy.typical_turn_words,
    responseOnsetMs: policy.response_onset_ms,
  };
}

function evaluateInitiative(): void {
  const runtime = liveConversationStore.getState();
  const profile = runtime.profile ?? readEffectiveLiveConversationProfile();
  selectedSessionId = runtime.sessionId ?? selectedSessionId;
  callConnected = runtime.conversation.connection === 'connected';
  if (!profile || !selectedSessionId) return;
  const policy = runtime.presencePolicy?.preset === profile.presence_preset
    ? runtime.presencePolicy.values
    : null;
  const timing = resolveInitiativePolicyTiming(profile.idle_threshold_ms, policy);
  const transcript = currentDraftOrTranscript();
  const userSpeaking = runtime.conversation.userTurn === 'speaking'
    || runtime.conversation.userTurn === 'speech_candidate';
  const reason = proactiveReasonFromTranscript(transcript)
    ?? (profile.long_pause_behavior === 'reassure'
      ? 'gentle_reassurance'
      : profile.long_pause_behavior === 'ask_to_continue'
        ? 'ask_to_continue'
        : null);
  const decision = decideInitiative({
    mode: profile.initiative_mode,
    callConnected,
    assistantActive: isAssistantSpeaking(),
    userSpeaking,
    partialTranscript: userSpeaking ? transcript : '',
    userRequestedTime: THINKING_PATTERN.test(transcript),
    sensitiveDictation: SENSITIVE_PATTERN.test(transcript),
    tabVisible: document.visibilityState === 'visible',
    muted: false,
    requestInFlight: Boolean(requestController || pending),
    hasMeaningfulReason: Boolean(reason),
    previousPromptIgnored,
    nowMs: performance.now(),
    lastActivityAtMs,
    lastPromptAtMs,
    idleThresholdMs: timing.idleThresholdMs,
    cooldownMs: timing.cooldownMs,
    promptCount,
    maxPrompts: profile.max_idle_prompts,
  });
  dispatchPerf('initiative_policy_decision', {
    action: decision.action,
    reason: decision.reason,
    eligible_in_ms: decision.eligibleInMs,
    presence_policy_version: runtime.presencePolicy?.version ?? null,
    idle_threshold_ms: timing.idleThresholdMs,
    cooldown_ms: timing.cooldownMs,
  });
  if (decision.action === 'speak' && reason && isAutoSpeakEnabled()) {
    void startProactiveTurn(selectedSessionId, reason, profile, timing);
  }
}

async function startProactiveTurn(
  sessionId: string,
  reason: string,
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
): Promise<void> {
  if (requestController || pending) return;
  const controller = new AbortController();
  requestController = controller;
  const params = new URLSearchParams({
    purpose: 'proactive_reengagement',
    initiative_reason: reason,
    state_summary: conversationStateSummary(profile, timing),
  });
  if (timing.typicalTurnWords !== null) params.set('target_words', String(timing.typicalTurnWords));
  dispatchPerf('initiative_generation_started', {
    session_id: sessionId,
    initiative_reason: reason,
    target_words: timing.typicalTurnWords,
  });
  try {
    if (timing.responseOnsetMs) await waitForOnset(timing.responseOnsetMs, controller.signal);
    const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/live-call/greeting/stream?${params}`, {
      method: 'POST',
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Proactive turn failed with status ${response.status}.`);
    const parsed = parseProactiveSse(await response.text());
    if (!parsed || controller.signal.aborted) return;
    const turn: PendingProactive = {
      sessionId,
      turnId: parsed.turnId,
      content: parsed.content,
      reason: parsed.initiativeReason || reason,
      audioStarted: isAssistantSpeaking(),
      committing: false,
    };
    pending = turn;
    dispatchPerf('initiative_generation_completed', { turn_id: parsed.turnId, content_chars: parsed.content.length });
    if (!turn.audioStarted) {
      audioStartTimer = setTimeout(() => {
        if (pending === turn && !turn.audioStarted) clearPending('audio-never-started');
      }, AUDIO_START_TIMEOUT_MS);
      setTimeout(handleAuthoritativeStateChange, 0);
    }
  } catch (error) {
    if (!controller.signal.aborted) dispatchPerf('initiative_generation_failed', {
      error: error instanceof Error ? error.message : String(error),
    });
  } finally {
    if (requestController === controller) requestController = null;
  }
}

function handleAuthoritativeStateChange(): void {
  const runtime = liveConversationStore.getState();
  selectedSessionId = runtime.sessionId ?? selectedSessionId;
  callConnected = runtime.conversation.connection === 'connected';
  const speaking = isAssistantSpeaking();
  if (speaking === assistantSpeaking) return;
  const wasSpeaking = assistantSpeaking;
  assistantSpeaking = speaking;
  lastActivityAtMs = performance.now();
  if (pending && speaking) {
    pending.audioStarted = true;
    clearAudioStartTimer();
  }
  if (pending?.audioStarted && wasSpeaking && !speaking) void commitPending('completed');
}

async function commitPending(status: 'completed' | 'interrupted'): Promise<void> {
  const turn = pending;
  if (!turn || turn.committing) return;
  turn.committing = true;
  clearAudioStartTimer();
  try {
    const response = await fetch(`/api/chat/sessions/${encodeURIComponent(turn.sessionId)}/live-conversation/proactive/delivery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        turn_id: turn.turnId,
        content: turn.content,
        initiative_reason: turn.reason,
        delivery_status: status,
      }),
    });
    if (!response.ok) throw new Error(`Proactive delivery commit failed with status ${response.status}.`);
    promptCount += 1;
    lastPromptAtMs = performance.now();
    lastActivityAtMs = lastPromptAtMs;
    window.dispatchEvent(new CustomEvent(DELIVERED_EVENT, {
      detail: { sessionId: turn.sessionId, turnId: turn.turnId, status },
    }));
    dispatchPerf('initiative_delivery_committed', { turn_id: turn.turnId, delivery_status: status });
  } catch (error) {
    dispatchPerf('initiative_delivery_commit_failed', {
      error: error instanceof Error ? error.message : String(error),
    });
  } finally {
    if (pending === turn) pending = null;
  }
}

function resetQuietPeriod(reason: string): void {
  requestController?.abort(reason);
  requestController = null;
  clearPending(reason);
  promptCount = 0;
  previousPromptIgnored = false;
  lastPromptAtMs = null;
  lastActivityAtMs = performance.now();
}

function clearPending(reason: string): void {
  if (pending) dispatchPerf('initiative_pending_cleared', { turn_id: pending.turnId, reason });
  pending = null;
  clearAudioStartTimer();
}

function clearAudioStartTimer(): void {
  if (audioStartTimer !== null) clearTimeout(audioStartTimer);
  audioStartTimer = null;
}

function currentDraftOrTranscript(): string {
  const transcript = liveConversationStore.getState().transcript;
  return transcript.partial || transcript.lastFinal;
}

function conversationStateSummary(
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
): string {
  const runtime = liveConversationStore.getState();
  const messages = runtime.transcript.recentFinals
    .slice(-3)
    .map((value) => value.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  return [
    `stance=${profile.conversation_stance}`,
    `presence=${profile.presence_preset}`,
    `policy_version=${runtime.presencePolicy?.version ?? 'none'}`,
    `target_words=${timing.typicalTurnWords ?? 'profile'}`,
    `recent=${messages.join(' | ')}`,
  ].join('; ').slice(0, 500);
}

function isAssistantSpeaking(): boolean {
  const conversation = liveConversationStore.getState().conversation;
  return conversation.assistantTurn === 'speaking' || conversation.delivery === 'audio_started';
}

function isAutoSpeakEnabled(): boolean {
  return document.querySelector<HTMLInputElement>('.assistant-voice-toggle input[type="checkbox"]')?.checked ?? false;
}

function waitForOnset(delayMs: number, signal: AbortSignal): Promise<void> {
  const bounded = Math.max(0, Math.min(5_000, delayMs));
  if (!bounded || signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, bounded);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

function dispatchPerf(stage: string, details: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...details },
  }));
}
