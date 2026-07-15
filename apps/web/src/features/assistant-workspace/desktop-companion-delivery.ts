import { liveConversationStore, type LiveConversationRuntimeState } from './live-conversation-store';

export const DESKTOP_COMPANION_DELIVERY_REQUEST_EVENT = 'omnix:desktop-companion-delivery-request';
export const DESKTOP_COMPANION_DELIVERY_EVENT = 'omnix:desktop-companion-delivery';

const USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const PERF_EVENT = 'omnix:assistant-voice-perf';

type DesktopCompanionWindow = Window & typeof globalThis & {
  __omnixDesktopCompanionDeliveryInstalled?: boolean;
};

export type DesktopCompanionDeliveryRequest = {
  sessionId: string;
  observationId: string;
  groundingIds: string[];
  stateSummary: string;
  priority: 'normal' | 'critical';
  expiresAtMs: number;
};

export type DesktopCompanionDeliveryDecision = {
  action: 'deliver' | 'wait' | 'suppress';
  reason: string;
};

type ParsedDesktopTurn = {
  turnId: string;
  content: string;
  purpose: 'desktop_companion' | 'desktop_critical';
};

type PendingDesktopTurn = ParsedDesktopTurn & {
  sessionId: string;
  observationId: string;
  groundingIds: string[];
  audioStarted: boolean;
  committing: boolean;
};

let requestController: AbortController | null = null;
let pending: PendingDesktopTurn | null = null;
let assistantSpeaking = false;

export function decideDesktopCompanionDelivery(
  request: DesktopCompanionDeliveryRequest,
  runtime: LiveConversationRuntimeState,
  options: { nowMs: number; requestInFlight: boolean; autoSpeak: boolean },
): DesktopCompanionDeliveryDecision {
  if (!request.sessionId || !request.observationId) return suppress('invalid_request');
  if (options.nowMs >= request.expiresAtMs) return suppress('candidate_stale');
  if (runtime.sessionId && runtime.sessionId !== request.sessionId) return suppress('session_mismatch');
  if (!options.autoSpeak) return suppress('auto_speak_disabled');
  if (options.requestInFlight) return wait('delivery_request_active');
  const conversation = runtime.conversation;
  if (
    conversation.userTurn === 'speaking'
    || conversation.userTurn === 'speech_candidate'
    || conversation.floorOwner === 'user'
  ) return wait('user_floor_active');
  if (
    conversation.assistantTurn === 'planning'
    || conversation.assistantTurn === 'generating'
    || conversation.assistantTurn === 'queued'
    || conversation.assistantTurn === 'speaking'
    || conversation.delivery === 'audio_started'
    || conversation.floorOwner === 'assistant'
  ) return wait('assistant_busy');
  if (conversation.bargeIn !== 'inactive' && conversation.bargeIn !== 'rejected') return wait('barge_in_active');
  if (conversation.initiative === 'considering' || conversation.initiative === 'prompting') return wait('social_initiative_active');
  return { action: 'deliver', reason: 'desktop_candidate_eligible' };
}

export function initializeDesktopCompanionDeliveryController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const target = window as DesktopCompanionWindow;
  if (target.__omnixDesktopCompanionDeliveryInstalled) return () => undefined;
  target.__omnixDesktopCompanionDeliveryInstalled = true;
  assistantSpeaking = isAssistantSpeaking(liveConversationStore.getState());

  const handleRequest = (event: Event) => {
    const request = normalizeRequest((event as CustomEvent<unknown>).detail);
    if (!request) return;
    const decision = decideDesktopCompanionDelivery(request, liveConversationStore.getState(), {
      nowMs: Date.now(),
      requestInFlight: Boolean(requestController || pending),
      autoSpeak: isAutoSpeakEnabled(),
    });
    dispatchPerf('desktop_companion_delivery_decision', {
      action: decision.action,
      reason: decision.reason,
      observation_id: request.observationId,
      priority: request.priority,
    });
    if (decision.action === 'deliver') void startDesktopTurn(request);
    else dispatchDelivery(decision.action, request, { reason: decision.reason });
  };
  const handleUserSpeech = () => cancelActive('user_speech', true);
  const handleInterrupt = () => cancelActive('interrupted', true);
  const handleStop = () => cancelActive('live_voice_stopped', false);

  window.addEventListener(DESKTOP_COMPANION_DELIVERY_REQUEST_EVENT, handleRequest);
  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(INTERRUPT_EVENT, handleInterrupt);
  window.addEventListener(STOP_EVENT, handleStop);
  const unsubscribe = liveConversationStore.subscribe(handleAuthoritativeStateChange);

  return () => {
    window.removeEventListener(DESKTOP_COMPANION_DELIVERY_REQUEST_EVENT, handleRequest);
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(INTERRUPT_EVENT, handleInterrupt);
    window.removeEventListener(STOP_EVENT, handleStop);
    unsubscribe();
    cancelActive('controller_disposed', false);
    target.__omnixDesktopCompanionDeliveryInstalled = false;
  };
}

async function startDesktopTurn(request: DesktopCompanionDeliveryRequest): Promise<void> {
  if (requestController || pending) return;
  const controller = new AbortController();
  requestController = controller;
  const purpose = request.priority === 'critical' ? 'desktop_critical' : 'desktop_companion';
  const params = new URLSearchParams({
    purpose: 'proactive_reengagement',
    initiative_reason: `${purpose}:${request.observationId}`,
    state_summary: request.stateSummary.replace(/\s+/g, ' ').trim().slice(0, 500),
  });
  dispatchPerf('desktop_companion_generation_started', {
    session_id: request.sessionId,
    observation_id: request.observationId,
    purpose,
  });
  try {
    const response = await fetch(
      `/api/chat/sessions/${encodeURIComponent(request.sessionId)}/live-call/greeting/stream?${params}`,
      { method: 'POST', signal: controller.signal },
    );
    if (!response.ok) throw new Error(`Desktop companion turn failed with status ${response.status}.`);
    const parsed = parseDesktopCompanionSse(await response.text());
    if (!parsed || controller.signal.aborted) return;
    if (parsed.content.trim().toUpperCase().replace(/[.!]+$/, '') === 'SKIP') {
      dispatchDelivery('suppress', request, { reason: 'model_skip', turnId: parsed.turnId });
      return;
    }
    const turn: PendingDesktopTurn = {
      ...parsed,
      sessionId: request.sessionId,
      observationId: request.observationId,
      groundingIds: request.groundingIds.slice(0, 16),
      audioStarted: isAssistantSpeaking(liveConversationStore.getState()),
      committing: false,
    };
    pending = turn;
    dispatchDelivery('generated', request, { turnId: turn.turnId, content: turn.content });
    handleAuthoritativeStateChange();
  } catch (error) {
    if (!controller.signal.aborted) {
      dispatchDelivery('error', request, { reason: error instanceof Error ? error.message : String(error) });
      dispatchPerf('desktop_companion_generation_failed', {
        observation_id: request.observationId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  } finally {
    if (requestController === controller) requestController = null;
  }
}

export function parseDesktopCompanionSse(text: string): ParsedDesktopTurn | null {
  let turnId = '';
  let content = '';
  let purpose: ParsedDesktopTurn['purpose'] = 'desktop_companion';
  for (const block of text.split(/\n\n+/)) {
    const data = block.split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) continue;
    let event: Record<string, unknown>;
    try { event = JSON.parse(data) as Record<string, unknown>; } catch { continue; }
    if (event.type === 'error') throw new Error(String(event.message || 'Desktop companion turn failed.'));
    if (event.type === 'initiative' && typeof event.turn_id === 'string') turnId = event.turn_id;
    if (event.type !== 'complete') continue;
    if (typeof event.content === 'string') content = event.content.trim();
    const metadata = event.metadata as Record<string, unknown> | undefined;
    if (!turnId && typeof metadata?.turn_id === 'string') turnId = metadata.turn_id;
    if (metadata?.purpose === 'desktop_critical') purpose = 'desktop_critical';
  }
  return turnId && content ? { turnId, content, purpose } : null;
}

function handleAuthoritativeStateChange(): void {
  const speaking = isAssistantSpeaking(liveConversationStore.getState());
  if (speaking === assistantSpeaking) return;
  const wasSpeaking = assistantSpeaking;
  assistantSpeaking = speaking;
  if (pending && speaking) pending.audioStarted = true;
  if (pending?.audioStarted && wasSpeaking && !speaking) void commitPending('completed');
}

function cancelActive(reason: string, interrupted: boolean): void {
  requestController?.abort(reason);
  requestController = null;
  if (pending?.audioStarted && interrupted) void commitPending('interrupted');
  else if (pending) {
    dispatchDelivery('discarded', pendingRequest(pending), { reason, turnId: pending.turnId });
    pending = null;
  }
}

async function commitPending(status: 'completed' | 'interrupted'): Promise<void> {
  const turn = pending;
  if (!turn || turn.committing) return;
  turn.committing = true;
  try {
    const response = await fetch(`/api/chat/sessions/${encodeURIComponent(turn.sessionId)}/live-conversation/proactive/delivery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        turn_id: turn.turnId,
        content: turn.content,
        initiative_reason: `${turn.purpose}:${turn.observationId}`,
        purpose: turn.purpose,
        observation_id: turn.observationId,
        grounding_ids: turn.groundingIds,
        delivery_status: status,
      }),
    });
    if (!response.ok) throw new Error(`Desktop delivery commit failed with status ${response.status}.`);
    dispatchDelivery(status, pendingRequest(turn), { turnId: turn.turnId, content: turn.content });
    dispatchPerf('desktop_companion_delivery_committed', {
      turn_id: turn.turnId,
      observation_id: turn.observationId,
      delivery_status: status,
    });
  } catch (error) {
    dispatchDelivery('error', pendingRequest(turn), { reason: error instanceof Error ? error.message : String(error) });
  } finally {
    if (pending === turn) pending = null;
  }
}

function normalizeRequest(value: unknown): DesktopCompanionDeliveryRequest | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  const sessionId = typeof input.sessionId === 'string' ? input.sessionId.trim() : '';
  const observationId = typeof input.observationId === 'string' ? input.observationId.trim() : '';
  const stateSummary = typeof input.stateSummary === 'string' ? input.stateSummary.trim() : '';
  const expiresAtMs = Number(input.expiresAtMs);
  if (!sessionId || !observationId || !stateSummary || !Number.isFinite(expiresAtMs)) return null;
  return {
    sessionId,
    observationId,
    stateSummary: stateSummary.slice(0, 500),
    expiresAtMs,
    priority: input.priority === 'critical' ? 'critical' : 'normal',
    groundingIds: Array.isArray(input.groundingIds)
      ? input.groundingIds.filter((item): item is string => typeof item === 'string').slice(0, 16)
      : [observationId],
  };
}

function pendingRequest(turn: PendingDesktopTurn): DesktopCompanionDeliveryRequest {
  return {
    sessionId: turn.sessionId,
    observationId: turn.observationId,
    groundingIds: turn.groundingIds,
    stateSummary: '',
    priority: turn.purpose === 'desktop_critical' ? 'critical' : 'normal',
    expiresAtMs: Number.POSITIVE_INFINITY,
  };
}

function isAssistantSpeaking(runtime: LiveConversationRuntimeState): boolean {
  return runtime.conversation.assistantTurn === 'speaking' || runtime.conversation.delivery === 'audio_started';
}

function isAutoSpeakEnabled(): boolean {
  return document.querySelector<HTMLInputElement>('.assistant-voice-toggle input[type="checkbox"]')?.checked ?? false;
}

function wait(reason: string): DesktopCompanionDeliveryDecision {
  return { action: 'wait', reason };
}

function suppress(reason: string): DesktopCompanionDeliveryDecision {
  return { action: 'suppress', reason };
}

function dispatchDelivery(
  status: string,
  request: DesktopCompanionDeliveryRequest,
  details: Record<string, unknown> = {},
): void {
  window.dispatchEvent(new CustomEvent(DESKTOP_COMPANION_DELIVERY_EVENT, {
    detail: { status, sessionId: request.sessionId, observationId: request.observationId, ...details },
  }));
}

function dispatchPerf(stage: string, details: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...details },
  }));
}
