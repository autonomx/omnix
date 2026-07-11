import type { LiveConversationState } from './live-conversation-state';
import { liveConversationStore } from './live-conversation-store';
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
  if (typeof document === 'undefined') return () => undefined;
  const project = () => {
    const runtime = liveConversationStore.getState();
    const cue = deriveAvatarPresenceCue(runtime.conversation, runtime.deliveryPlan);
    document.querySelectorAll<HTMLElement>(
      '.assistant-voice-orb, [data-character-avatar], .character-avatar',
    ).forEach((node) => {
      node.dataset.presenceCue = cue;
    });
  };
  const unsubscribe = liveConversationStore.subscribe(project);
  // This observer only applies current store output to newly mounted presentation nodes.
  // It never infers conversation state from the DOM.
  const observer = new MutationObserver(project);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  project();
  return () => {
    unsubscribe();
    observer.disconnect();
  };
}
