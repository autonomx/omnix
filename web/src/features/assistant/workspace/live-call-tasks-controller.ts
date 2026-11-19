import { useSyncExternalStore } from 'react';

import { unwrap } from '../../../api/http';
import {
  ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT,
  ASSISTANT_LIVE_VOICE_CALL_START_EVENT,
  ASSISTANT_LIVE_VOICE_STOP_EVENT,
  ASSISTANT_VOICE_PERF_EVENT,
  emitOmnixEvent,
  LIVE_CHAT_SESSION_CHANGED_EVENT,
  LIVE_CONVERSATION_PROACTIVE_DELIVERED_EVENT,
} from '../../../events/bus';
import { api } from '../api/gateway';
import type { components } from '../api/generated';
import { liveConversationStore } from './live-conversation-store';

/**
 * The tasks a live call asked for (live companion roadmap WP 1.4). The server owns each task's state; this module
 * only mirrors it for the call card and tells the initiative controller when a settled task waits for its report.
 */
export type LiveCallTask = components['schemas']['CallTask'];

export type LiveCallTasksState = {
  sessionId: string | null;
  tasks: LiveCallTask[];
  /** Tasks whose cancel request is on its way. */
  cancelling: string[];
};

/** How often an open task's state is read while the call waits for it. */
export const LIVE_CALL_TASK_POLL_MS = 5_000;

let state: LiveCallTasksState = { sessionId: null, tasks: [], cancelling: [] };
const listeners = new Set<() => void>();
let installed = false;
let callConnected = false;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let refreshRequest: Promise<void> | null = null;
let refreshAgain = false;
let assistantSpeaking = false;

function setState(change: Partial<LiveCallTasksState>): void {
  state = { ...state, ...change };
  listeners.forEach((listener) => listener());
}

export const liveCallTasksStore = {
  getState(): LiveCallTasksState {
    return state;
  },

  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  resetForTests(): void {
    clearPollTimer();
    refreshRequest = null;
    refreshAgain = false;
    callConnected = false;
    assistantSpeaking = false;
    state = { sessionId: null, tasks: [], cancelling: [] };
    listeners.forEach((listener) => listener());
  },
};

export function openCallTasks(current: LiveCallTasksState = state): LiveCallTask[] {
  return current.tasks.filter((task) => task.state === 'open');
}

/** Settled tasks the call has not told yet. A cancelled task needs no report. */
export function callTasksAwaitingReport(sessionId: string, current: LiveCallTasksState = state): LiveCallTask[] {
  if (current.sessionId !== sessionId) return [];
  return current.tasks.filter((task) => task.state !== 'open' && task.state !== 'cancelled' && !task.reported);
}

export function useLiveCallTasks(): LiveCallTasksState {
  return useSyncExternalStore(liveCallTasksStore.subscribe, liveCallTasksStore.getState, liveCallTasksStore.getState);
}

export function initializeLiveCallTasksController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  if (installed) return () => undefined;
  installed = true;
  const runtime = liveConversationStore.getState();
  callConnected = runtime.conversation.connection === 'connected';
  assistantSpeaking = isAssistantSpeaking();
  adoptSession(runtime.sessionId);
  if (callConnected) void refreshLiveCallTasks();

  const handleSession = (event: Event) => {
    const detail = (event as CustomEvent<{ sessionId?: unknown }>).detail;
    if (typeof detail?.sessionId === 'string') adoptSession(detail.sessionId);
    if (callConnected) void refreshLiveCallTasks();
  };
  const handleCallStart = () => {
    callConnected = false;
    clearPollTimer();
    setState({ tasks: [], cancelling: [] });
  };
  const handleCallConnected = () => {
    callConnected = true;
    void refreshLiveCallTasks();
  };
  const handleStop = () => {
    callConnected = false;
    clearPollTimer();
    setState({ tasks: [], cancelling: [] });
  };
  // A delivered report changes a task's `reported`; read it before the next report is chosen.
  const handleDelivered = () => { if (callConnected) void refreshLiveCallTasks(); };

  window.addEventListener(LIVE_CHAT_SESSION_CHANGED_EVENT, handleSession);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleCallStart);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, handleCallConnected);
  window.addEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
  window.addEventListener(LIVE_CONVERSATION_PROACTIVE_DELIVERED_EVENT, handleDelivered);
  const unsubscribe = liveConversationStore.subscribe(handleRuntimeChange);

  return () => {
    unsubscribe();
    window.removeEventListener(LIVE_CHAT_SESSION_CHANGED_EVENT, handleSession);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleCallStart);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, handleCallConnected);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
    window.removeEventListener(LIVE_CONVERSATION_PROACTIVE_DELIVERED_EVENT, handleDelivered);
    clearPollTimer();
    installed = false;
  };
}

/** Reads the call's tasks once, then keeps reading every 5 s while one is open. */
export function refreshLiveCallTasks(): Promise<void> {
  if (refreshRequest) {
    refreshAgain = true;
    return refreshRequest;
  }
  const sessionId = state.sessionId;
  if (!sessionId) return Promise.resolve();
  clearPollTimer();
  refreshRequest = (async () => {
    try {
      const data = await unwrap(api.GET('/api/chat/sessions/{session_id}/live-call/tasks', {
        params: { path: { session_id: sessionId } },
        cache: 'no-store',
      }));
      if (state.sessionId !== sessionId) return;
      const known = new Set(data.tasks.map((task) => task.task_id));
      setState({ tasks: data.tasks, cancelling: state.cancelling.filter((id) => known.has(id)) });
    } catch (error) {
      dispatchPerf('call_tasks_refresh_failed', { error: error instanceof Error ? error.message : String(error) });
    }
  })().finally(() => {
    refreshRequest = null;
    if (refreshAgain) {
      refreshAgain = false;
      void refreshLiveCallTasks();
      return;
    }
    schedulePoll();
  });
  return refreshRequest;
}

export async function cancelLiveCallTask(taskId: string): Promise<void> {
  const sessionId = state.sessionId;
  if (!sessionId || state.cancelling.includes(taskId)) return;
  setState({ cancelling: [...state.cancelling, taskId] });
  try {
    const task = await unwrap(api.POST('/api/chat/sessions/{session_id}/live-call/tasks/{task_id}/cancel', {
      params: { path: { session_id: sessionId, task_id: taskId } },
    }));
    if (state.sessionId === sessionId) {
      setState({ tasks: state.tasks.map((item) => (item.task_id === task.task_id ? task : item)) });
    }
  } catch (error) {
    dispatchPerf('call_task_cancel_failed', { error: error instanceof Error ? error.message : String(error) });
  } finally {
    setState({ cancelling: state.cancelling.filter((id) => id !== taskId) });
    void refreshLiveCallTasks();
  }
}

function adoptSession(sessionId: string | null): void {
  if (sessionId === state.sessionId) return;
  clearPollTimer();
  setState({ sessionId, tasks: [], cancelling: [] });
}

// A reply that asked for a task has been committed by the time its audio ends: read the list then.
function handleRuntimeChange(): void {
  const runtime = liveConversationStore.getState();
  if (runtime.sessionId && runtime.sessionId !== state.sessionId) adoptSession(runtime.sessionId);
  callConnected = runtime.conversation.connection === 'connected';
  if (!callConnected) clearPollTimer();
  const speaking = isAssistantSpeaking();
  const finishedSpeaking = assistantSpeaking && !speaking;
  assistantSpeaking = speaking;
  if (finishedSpeaking && callConnected) void refreshLiveCallTasks();
}

function schedulePoll(): void {
  clearPollTimer();
  if (!callConnected || !state.sessionId || !openCallTasks().length) return;
  pollTimer = setTimeout(() => {
    pollTimer = null;
    void refreshLiveCallTasks();
  }, LIVE_CALL_TASK_POLL_MS);
}

function clearPollTimer(): void {
  if (pollTimer !== null) clearTimeout(pollTimer);
  pollTimer = null;
}

function isAssistantSpeaking(): boolean {
  const conversation = liveConversationStore.getState().conversation;
  return conversation.assistantTurn === 'speaking' || conversation.delivery === 'audio_started';
}

function dispatchPerf(stage: string, details: Record<string, unknown>): void {
  emitOmnixEvent(ASSISTANT_VOICE_PERF_EVENT, { stage, timestamp: new Date().toISOString(), ...details });
}
