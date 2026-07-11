import {
  evaluateLiveConversation,
  type LiveConversationEvaluationEvent,
  type LiveConversationEvaluationReport,
} from './live-conversation-evaluation';

export const LIVE_EVALUATION_UPDATED_EVENT = 'omnix:live-conversation-evaluation-updated';
export const LIVE_EVALUATION_STORAGE_KEY = 'omnix.liveConversation.evaluation.v1';
const PERF_EVENT = 'omnix:assistant-voice-perf';
const CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const PROACTIVE_DELIVERED_EVENT = 'omnix:live-conversation-proactive-delivered';
const REPAIR_EVENT = 'omnix:live-conversation-repair-planned';
const LISTENER_BACKCHANNEL_EVENT = 'omnix:live-conversation-listener-backchannel';
const MAX_EVENTS = 600;
const PROACTIVE_REGRET_WINDOW_MS = 2_500;
const BACKCHANNEL_COLLISION_WINDOW_MS = 650;

type EvaluationWindow = Window & typeof globalThis & {
  __omnixLiveConversationEvaluationInstalled?: boolean;
};

type PerfDetail = Record<string, unknown> & { stage?: unknown };

type EvaluationSnapshot = {
  events: LiveConversationEvaluationEvent[];
  report: LiveConversationEvaluationReport;
};

let events: LiveConversationEvaluationEvent[] = [];
let userSpeechStartedAt: number | null = null;
let overlapStartedAt: number | null = null;
let lastProactiveAt: number | null = null;
let pendingRepair = false;
let pendingObligation = false;
let lastAssistantContent = '';
let listenerBackchannelAt: number | null = null;
let listenerBackchannelTimer: ReturnType<typeof setTimeout> | null = null;
const seenTranscriptRows = new WeakSet<Element>();

export function initializeLiveConversationEvaluationController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const liveWindow = window as EvaluationWindow;
  if (liveWindow.__omnixLiveConversationEvaluationInstalled) return () => undefined;
  liveWindow.__omnixLiveConversationEvaluationInstalled = true;
  events = readStoredEvents();
  markExistingTranscriptRows();

  const handleCallStart = () => resetLiveConversationEvaluation();
  const handleStop = () => {
    if (pendingRepair) recordLiveConversationEvaluationEvent({ atMs: now(), type: 'repair', success: false });
    if (pendingObligation) recordLiveConversationEvaluationEvent({ atMs: now(), type: 'obligation', answered: false });
    pendingRepair = false;
    pendingObligation = false;
    resolveBackchannel(false);
  };
  const handleUserSpeech = () => {
    const timestamp = now();
    userSpeechStartedAt ??= timestamp;
    if (lastProactiveAt !== null) {
      recordLiveConversationEvaluationEvent({
        atMs: timestamp,
        type: 'proactive_prompt',
        accepted: timestamp - lastProactiveAt > PROACTIVE_REGRET_WINDOW_MS,
      });
      lastProactiveAt = null;
    }
    if (listenerBackchannelAt !== null && timestamp - listenerBackchannelAt <= BACKCHANNEL_COLLISION_WINDOW_MS) {
      resolveBackchannel(true);
    }
  };
  const handleProactive = () => {
    lastProactiveAt = now();
    recordLiveConversationEvaluationEvent({ atMs: lastProactiveAt, type: 'proactive_prompt', accepted: null });
  };
  const handleRepair = () => { pendingRepair = true; };
  const handleListenerBackchannel = () => {
    resolveBackchannel(false, false);
    listenerBackchannelAt = now();
    listenerBackchannelTimer = setTimeout(() => resolveBackchannel(false), BACKCHANNEL_COLLISION_WINDOW_MS);
  };
  const handlePerf = (event: Event) => {
    const detail = (event as CustomEvent<PerfDetail>).detail ?? {};
    const mapped = evaluationEventFromPerfDetail(detail, now());
    if (mapped) recordLiveConversationEvaluationEvent(mapped);
    const stage = String(detail.stage ?? '');
    if (stage === 'overlap_candidate') overlapStartedAt = now();
    if (stage === 'overlap_classified' && overlapStartedAt !== null) {
      recordLiveConversationEvaluationEvent({
        atMs: now(),
        type: 'talk_over',
        durationMs: Math.max(0, now() - overlapStartedAt),
      });
      overlapStartedAt = null;
    }
    if (stage === 'stt_final_received' && userSpeechStartedAt !== null) {
      recordTurn('user', Math.max(100, now() - userSpeechStartedAt), currentTranscriptText());
      userSpeechStartedAt = null;
      if (pendingObligation) {
        recordLiveConversationEvaluationEvent({ atMs: now(), type: 'obligation', answered: true });
        pendingObligation = false;
      }
    }
    if (stage === 'voice_audio_turnaround' && pendingRepair) {
      recordLiveConversationEvaluationEvent({ atMs: now(), type: 'repair', success: true });
      pendingRepair = false;
    }
  };

  window.addEventListener(CALL_START_EVENT, handleCallStart);
  window.addEventListener(STOP_EVENT, handleStop);
  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(PROACTIVE_DELIVERED_EVENT, handleProactive);
  window.addEventListener(REPAIR_EVENT, handleRepair);
  window.addEventListener(LISTENER_BACKCHANNEL_EVENT, handleListenerBackchannel);
  window.addEventListener(PERF_EVENT, handlePerf);
  const observer = new MutationObserver(collectTranscriptRows);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  collectTranscriptRows();
  dispatchUpdate();

  return () => {
    observer.disconnect();
    window.removeEventListener(CALL_START_EVENT, handleCallStart);
    window.removeEventListener(STOP_EVENT, handleStop);
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(PROACTIVE_DELIVERED_EVENT, handleProactive);
    window.removeEventListener(REPAIR_EVENT, handleRepair);
    window.removeEventListener(LISTENER_BACKCHANNEL_EVENT, handleListenerBackchannel);
    window.removeEventListener(PERF_EVENT, handlePerf);
    resolveBackchannel(false, false);
    liveWindow.__omnixLiveConversationEvaluationInstalled = false;
  };
}

export function evaluationEventFromPerfDetail(
  detail: PerfDetail,
  atMs: number,
): LiveConversationEvaluationEvent | null {
  const stage = String(detail.stage ?? '');
  if (stage === 'voice_audio_turnaround') {
    const latency = numberValue(detail.total_ms ?? detail.totalMs);
    return latency === null ? null : { atMs, type: 'first_audio', latencyMs: latency };
  }
  if (stage === 'endpoint_false_positive') return { atMs, type: 'endpoint', falsePositive: true };
  if (stage === 'endpoint_committed') return { atMs, type: 'endpoint', falsePositive: false };
  if (stage === 'talk_over') {
    const duration = numberValue(detail.duration_ms ?? detail.durationMs);
    return duration === null ? null : { atMs, type: 'talk_over', durationMs: duration };
  }
  if (stage === 'overlap_classified') {
    const intent = String(detail.intent ?? '');
    if (!['interrupt', 'hard_stop', 'correction', 'question'].includes(intent)) return null;
    const latency = numberValue(detail.cancellation_latency_ms ?? detail.cancel_ms ?? detail.latency_ms);
    return { atMs, type: 'interruption', success: true, ...(latency === null ? {} : { latencyMs: latency }) };
  }
  if (stage === 'barge_in_rejected') return { atMs, type: 'interruption', success: false };
  return null;
}

export function recordLiveConversationEvaluationEvent(event: LiveConversationEvaluationEvent): EvaluationSnapshot {
  events = [...events, sanitizeEvent(event)].sort((left, right) => left.atMs - right.atMs).slice(-MAX_EVENTS);
  persistEvents(events);
  return dispatchUpdate();
}

export function recordLiveConversationSurvey(listeningScore: number, pressureScore: number): EvaluationSnapshot {
  return recordLiveConversationEvaluationEvent({
    atMs: now(),
    type: 'survey',
    listeningScore,
    pressureScore,
  });
}

export function readLiveConversationEvaluationSnapshot(): EvaluationSnapshot {
  const current = events.length ? events : readStoredEvents();
  return { events: [...current], report: evaluateLiveConversation(current) };
}

export function resetLiveConversationEvaluation(): EvaluationSnapshot {
  events = [];
  userSpeechStartedAt = null;
  overlapStartedAt = null;
  lastProactiveAt = null;
  pendingRepair = false;
  pendingObligation = false;
  lastAssistantContent = '';
  resolveBackchannel(false, false);
  persistEvents(events);
  markExistingTranscriptRows();
  return dispatchUpdate();
}

function collectTranscriptRows(): void {
  document.querySelectorAll<Element>('.assistant-voice-transcript p:not(.muted)').forEach((row) => {
    if (seenTranscriptRows.has(row)) return;
    seenTranscriptRows.add(row);
    const role = row.classList.contains('assistant') ? 'assistant' : row.classList.contains('user') ? 'user' : null;
    if (!role) return;
    const content = transcriptRowText(row);
    if (!content) return;
    if (role === 'assistant') {
      const durationMs = estimateSpokenDuration(content, 2.45);
      recordTurn('assistant', durationMs, content);
      const repeated = Boolean(lastAssistantContent) && lexicalSimilarity(content, lastAssistantContent) >= 0.72;
      recordLiveConversationEvaluationEvent({ atMs: now(), type: 'topic', repeated });
      lastAssistantContent = content;
      if (/[?？]\s*$/.test(content)) pendingObligation = true;
    }
  });
}

function recordTurn(role: 'user' | 'assistant', durationMs: number, content: string): void {
  recordLiveConversationEvaluationEvent({
    atMs: now(),
    type: 'turn',
    role,
    durationMs,
    content: content.slice(0, 280),
  });
}

function resolveBackchannel(collision: boolean, record = true): void {
  if (listenerBackchannelTimer) clearTimeout(listenerBackchannelTimer);
  listenerBackchannelTimer = null;
  if (record && listenerBackchannelAt !== null) {
    recordLiveConversationEvaluationEvent({ atMs: now(), type: 'backchannel', collision });
  }
  listenerBackchannelAt = null;
}

function markExistingTranscriptRows(): void {
  document.querySelectorAll('.assistant-voice-transcript p:not(.muted)').forEach((row) => seenTranscriptRows.add(row));
}

function transcriptRowText(row: Element): string {
  const clone = row.cloneNode(true) as HTMLElement;
  clone.querySelector('span')?.remove();
  return clone.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

function currentTranscriptText(): string {
  const draft = document.querySelector<HTMLElement>('.assistant-live-draft p')?.textContent?.trim();
  if (draft && !draft.startsWith('Start Live Voice')) return draft;
  const rows = Array.from(document.querySelectorAll<Element>('.assistant-voice-transcript p.user'));
  return rows.length ? transcriptRowText(rows.at(-1) as Element) : '';
}

function estimateSpokenDuration(content: string, wordsPerSecond: number): number {
  const words = content.split(/\s+/).filter(Boolean).length;
  return Math.max(350, Math.round(words / wordsPerSecond * 1_000));
}

function lexicalSimilarity(left: string, right: string): number {
  const leftWords = new Set(normalizeWords(left));
  const rightWords = new Set(normalizeWords(right));
  if (!leftWords.size || !rightWords.size) return 0;
  const intersection = [...leftWords].filter((word) => rightWords.has(word)).length;
  return intersection / Math.max(leftWords.size, rightWords.size);
}

function normalizeWords(content: string): string[] {
  return content.toLocaleLowerCase().replace(/[^\p{L}\p{N}'\s]+/gu, ' ').split(/\s+/).filter((word) => word.length > 2);
}

function sanitizeEvent(event: LiveConversationEvaluationEvent): LiveConversationEvaluationEvent {
  if (event.type === 'turn') return { ...event, content: event.content.slice(0, 280) };
  return event;
}

function readStoredEvents(): LiveConversationEvaluationEvent[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LIVE_EVALUATION_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter(isEvaluationEvent).slice(-MAX_EVENTS) : [];
  } catch {
    return [];
  }
}

function persistEvents(value: LiveConversationEvaluationEvent[]): void {
  try { window.localStorage.setItem(LIVE_EVALUATION_STORAGE_KEY, JSON.stringify(value)); } catch { /* in-memory report remains available */ }
}

function dispatchUpdate(): EvaluationSnapshot {
  const snapshot = { events: [...events], report: evaluateLiveConversation(events) };
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(LIVE_EVALUATION_UPDATED_EVENT, { detail: snapshot }));
  return snapshot;
}

function isEvaluationEvent(value: unknown): value is LiveConversationEvaluationEvent {
  return Boolean(value && typeof value === 'object' && typeof (value as { atMs?: unknown }).atMs === 'number' && typeof (value as { type?: unknown }).type === 'string');
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : null;
}

function now(): number {
  return Date.now();
}
