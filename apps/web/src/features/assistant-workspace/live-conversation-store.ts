import { useSyncExternalStore } from 'react';

import type { LiveConversationProfile } from '../chatbot/liveConversationProfileClient';
import type { PresencePolicyVersion } from './live-chat-evaluation-client';
import {
  INITIAL_LIVE_CONVERSATION_STATE,
  deriveLiveConversationStatus,
  reduceLiveConversationState,
  type LiveConversationState,
  type LiveConversationStateEvent,
} from './live-conversation-state';
import type { LiveVoiceCalibrationRecord } from './live-voice-calibration';
import type { SpeechDeliveryPlan } from './live-speech-delivery-plan';

export const LIVE_CONVERSATION_STORE_UPDATED_EVENT = 'omnix:live-conversation-store-updated';

export type LiveConversationIdentity = {
  characterId: string;
  displayName: string;
  voiceId: string | null;
  profileVersion: number | null;
};

export type LiveConversationDuplexState = {
  configuredMode: 'automatic' | 'half_duplex' | 'echo_aware';
  resolvedMode: 'half_duplex' | 'echo_aware';
  reason: string;
  confidence: number;
  calibration: LiveVoiceCalibrationRecord | null;
};

export type LiveConversationTranscriptState = {
  partial: string;
  lastFinal: string;
  recentFinals: string[];
};

export type LiveConversationRuntimeState = {
  conversation: LiveConversationState;
  sessionId: string | null;
  identity: LiveConversationIdentity;
  profile: LiveConversationProfile | null;
  presencePolicy: PresencePolicyVersion | null;
  duplex: LiveConversationDuplexState;
  deliveryPlan: SpeechDeliveryPlan | null;
  pronunciationRevision: number;
  qualitySummary: Record<string, unknown> | null;
  transcript: LiveConversationTranscriptState;
};

export type LiveConversationStoreAction =
  | { type: 'conversation'; event: LiveConversationStateEvent }
  | { type: 'session'; sessionId: string | null }
  | { type: 'identity'; identity: Partial<LiveConversationIdentity> }
  | { type: 'profile'; profile: LiveConversationProfile | null }
  | { type: 'presence_policy'; policy: PresencePolicyVersion | null }
  | { type: 'duplex'; duplex: Partial<LiveConversationDuplexState> }
  | { type: 'delivery_plan'; plan: SpeechDeliveryPlan | null }
  | { type: 'pronunciation_revision'; revision: number }
  | { type: 'quality'; summary: Record<string, unknown> | null }
  | { type: 'transcript_partial'; text: string }
  | { type: 'transcript_final'; text: string }
  | { type: 'reset_conversation' }
  | { type: 'reset_all' };

export const INITIAL_LIVE_CONVERSATION_RUNTIME_STATE: LiveConversationRuntimeState = {
  conversation: INITIAL_LIVE_CONVERSATION_STATE,
  sessionId: null,
  identity: {
    characterId: 'system-assistant',
    displayName: 'System Assistant',
    voiceId: null,
    profileVersion: null,
  },
  profile: null,
  presencePolicy: null,
  duplex: {
    configuredMode: 'automatic',
    resolvedMode: 'half_duplex',
    reason: 'calibration_missing',
    confidence: 0,
    calibration: null,
  },
  deliveryPlan: null,
  pronunciationRevision: 0,
  qualitySummary: null,
  transcript: { partial: '', lastFinal: '', recentFinals: [] },
};

export function reduceLiveConversationRuntimeState(
  state: LiveConversationRuntimeState,
  action: LiveConversationStoreAction,
): LiveConversationRuntimeState {
  switch (action.type) {
    case 'conversation':
      return { ...state, conversation: reduceLiveConversationState(state.conversation, action.event) };
    case 'session':
      return { ...state, sessionId: action.sessionId };
    case 'identity':
      return { ...state, identity: { ...state.identity, ...action.identity } };
    case 'profile':
      return {
        ...state,
        profile: action.profile,
        presencePolicy: action.profile && state.presencePolicy?.preset === action.profile.presence_preset
          ? state.presencePolicy
          : null,
        duplex: action.profile
          ? { ...state.duplex, configuredMode: action.profile.duplex_mode }
          : state.duplex,
      };
    case 'presence_policy':
      return { ...state, presencePolicy: action.policy };
    case 'duplex':
      return { ...state, duplex: { ...state.duplex, ...action.duplex } };
    case 'delivery_plan':
      return { ...state, deliveryPlan: action.plan };
    case 'pronunciation_revision':
      return { ...state, pronunciationRevision: Math.max(0, action.revision) };
    case 'quality':
      return { ...state, qualitySummary: action.summary };
    case 'transcript_partial':
      return { ...state, transcript: { ...state.transcript, partial: action.text } };
    case 'transcript_final': {
      const text = action.text.trim();
      const recentFinals = text
        ? [...state.transcript.recentFinals, text].slice(-6)
        : state.transcript.recentFinals;
      return {
        ...state,
        transcript: { partial: '', lastFinal: text, recentFinals },
      };
    }
    case 'reset_conversation':
      return {
        ...state,
        conversation: INITIAL_LIVE_CONVERSATION_STATE,
        deliveryPlan: null,
        transcript: { partial: '', lastFinal: '', recentFinals: [] },
      };
    case 'reset_all':
      return INITIAL_LIVE_CONVERSATION_RUNTIME_STATE;
    default:
      return state;
  }
}

export type LiveConversationStore = {
  getState: () => LiveConversationRuntimeState;
  dispatch: (action: LiveConversationStoreAction) => void;
  subscribe: (listener: () => void) => () => void;
  reset: () => void;
};

export function createLiveConversationStore(
  initialState: LiveConversationRuntimeState = INITIAL_LIVE_CONVERSATION_RUNTIME_STATE,
): LiveConversationStore {
  let state = initialState;
  const listeners = new Set<() => void>();
  const notify = () => {
    for (const listener of listeners) listener();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(LIVE_CONVERSATION_STORE_UPDATED_EVENT, { detail: state }));
    }
  };
  return {
    getState: () => state,
    dispatch: (action) => {
      const next = reduceLiveConversationRuntimeState(state, action);
      if (next === state) return;
      state = next;
      notify();
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    reset: () => {
      state = INITIAL_LIVE_CONVERSATION_RUNTIME_STATE;
      notify();
    },
  };
}

export const liveConversationStore = createLiveConversationStore();

export function useLiveConversationState(): LiveConversationRuntimeState {
  return useSyncExternalStore(
    liveConversationStore.subscribe,
    liveConversationStore.getState,
    () => INITIAL_LIVE_CONVERSATION_RUNTIME_STATE,
  );
}

export function useLiveConversationSelector<T>(selector: (state: LiveConversationRuntimeState) => T): T {
  return selector(useLiveConversationState());
}

export function replayLiveConversationActions(
  actions: readonly LiveConversationStoreAction[],
  initialState: LiveConversationRuntimeState = INITIAL_LIVE_CONVERSATION_RUNTIME_STATE,
): LiveConversationRuntimeState {
  return actions.reduce(reduceLiveConversationRuntimeState, initialState);
}

export function selectLiveChatSnapshot(state: LiveConversationRuntimeState) {
  return {
    connected: state.conversation.connection === 'connected',
    connection: state.conversation.connection,
    identity: state.identity.displayName,
    state: deriveLiveConversationStatus(state.conversation, state.identity.displayName),
    floorOwner: state.conversation.floorOwner,
    duplexMode: state.duplex.resolvedMode,
    duplexReason: state.duplex.reason,
    calibrationConfidence: state.duplex.confidence,
    presencePolicyVersion: state.presencePolicy?.version ?? null,
  };
}
