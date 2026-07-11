import {
  projectLegacyLiveVoiceState,
  type LiveConversationState,
} from './live-conversation-state';
import type { SpeechDeliveryPlan } from './live-speech-delivery-plan';

export type AvatarPresenceCue = 'idle' | 'listening' | 'thinking' | 'speaking' | 'yielding' | 'restrained';

export function deriveAvatarPresenceCue(
  state: LiveConversationState,
  plan: SpeechDeliveryPlan | null = null,
): AvatarPresenceCue {
  if (state.connection === 'disconnected') return 'idle';
  if (state.bargeIn === 'accepted' || state.assistantTurn === 'interrupted') return 'yielding';
  if (plan && plan.energy === 'low' && plan.warmth === 'high') return 'restrained';
  if (state.userTurn === 'speaking' || state.userTurn === 'speech_candidate' || state.floorOwner === 'user') return 'listening';
  if (state.assistantTurn === 'planning' || state.assistantTurn === 'generating') return 'thinking';
  if (state.assistantTurn === 'speaking' || state.floorOwner === 'assistant') return 'speaking';
  return 'idle';
}

export function initializeLiveAvatarPresenceController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  let plan: SpeechDeliveryPlan | null = null;
  const handlePlan = (event: Event) => {
    plan = (event as CustomEvent<SpeechDeliveryPlan>).detail ?? null;
    project();
  };
  const project = () => {
    const card = document.querySelector<HTMLElement>('.assistant-live-card');
    const connected = Array.from(card?.querySelectorAll<HTMLButtonElement>('button') ?? [])
      .some((button) => button.textContent?.trim().toLocaleLowerCase() === 'end call');
    const legacyState = card?.querySelector<HTMLElement>('.assistant-live-state span')?.textContent?.trim()
      || card?.querySelector<HTMLElement>('.assistant-voice-status strong')?.textContent?.trim()
      || 'Idle';
    const state = projectLegacyLiveVoiceState(connected, legacyState);
    if (card?.dataset.bargeIn === 'accepted') state.bargeIn = 'accepted';
    const cue = deriveAvatarPresenceCue(state, plan);
    document.querySelectorAll<HTMLElement>('.assistant-voice-orb, [data-character-avatar], .character-avatar').forEach((node) => {
      node.dataset.presenceCue = cue;
    });
  };
  window.addEventListener('omnix:live-speech-delivery-plan', handlePlan);
  const observer = new MutationObserver(project);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['data-voice-mode', 'data-barge-in', 'data-live-voice-status'],
  });
  project();
  return () => {
    observer.disconnect();
    window.removeEventListener('omnix:live-speech-delivery-plan', handlePlan);
  };
}
