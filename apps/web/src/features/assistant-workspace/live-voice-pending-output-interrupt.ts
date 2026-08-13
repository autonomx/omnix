import { liveConversationStore } from './live-conversation-store';
import type { LiveConversationState } from './live-conversation-state';

const USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const PERF_EVENT = 'omnix:assistant-voice-perf';

type PendingOutputInterruptWindow = Window & typeof globalThis & {
  __omnixLiveVoicePendingOutputInterruptInstalled?: boolean;
};

type UserSpeechDetail = {
  assistantSpeaking?: boolean;
  assistantOwnsFloor?: boolean;
};

export function shouldInterruptPendingAssistantOutput(conversation: LiveConversationState): boolean {
  return conversation.connection === 'connected'
    && conversation.delivery !== 'audio_started'
    && (
      conversation.assistantTurn === 'planning'
      || conversation.assistantTurn === 'generating'
      || conversation.assistantTurn === 'queued'
      || conversation.assistantTurn === 'speaking'
    );
}

export function initializeLiveVoicePendingOutputInterrupt(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as PendingOutputInterruptWindow;
  if (liveWindow.__omnixLiveVoicePendingOutputInterruptInstalled) return () => undefined;
  liveWindow.__omnixLiveVoicePendingOutputInterruptInstalled = true;

  const handleUserSpeech = (event: Event): void => {
    const conversation = liveConversationStore.getState().conversation;
    if (!shouldInterruptPendingAssistantOutput(conversation)) return;
    const detail = (event as CustomEvent<UserSpeechDetail>).detail ?? {};
    window.dispatchEvent(new CustomEvent(PERF_EVENT, {
      detail: {
        stage: 'pending_output_cancelled_on_user_speech',
        timestamp: new Date().toISOString(),
        assistantTurn: conversation.assistantTurn,
        delivery: conversation.delivery,
        floorOwner: conversation.floorOwner,
        assistantSpeaking: Boolean(detail.assistantSpeaking),
        assistantOwnsFloor: Boolean(detail.assistantOwnsFloor),
      },
    }));
    window.dispatchEvent(new CustomEvent(INTERRUPT_EVENT, {
      detail: {
        source: 'pending-output-user-speech',
        intent: 'interrupt',
        confidence: 1,
        reason: 'user_speech_before_audio_started',
        timestamp: new Date().toISOString(),
      },
    }));
  };

  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  return () => {
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    liveWindow.__omnixLiveVoicePendingOutputInterruptInstalled = false;
  };
}
