import {
  DESKTOP_COMPANION_EXPRESSION_EVENT,
  type DesktopCompanionExpression,
} from './desktop-companion-delivery';
import type { LiveConversationState } from './live-conversation-state';
import { liveConversationStore } from './live-conversation-store';
import type { SpeechDeliveryPlan } from './live-speech-delivery-plan';

export type AvatarPresenceCue = 'idle' | 'listening' | 'thinking' | 'speaking' | 'yielding' | 'restrained';

type CompanionExpressionDetail = {
  active?: boolean;
  expression?: DesktopCompanionExpression;
  intensity?: number;
};

let companionExpression: DesktopCompanionExpression = 'neutral';
let companionExpressionIntensity = 0;

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
      node.dataset.companionExpression = companionExpression;
      node.dataset.companionIntensity = companionExpressionIntensity.toFixed(2);
    });
  };
  const handleExpression = (event: Event) => {
    const detail = (event as CustomEvent<CompanionExpressionDetail>).detail ?? {};
    if (detail.active === false) {
      companionExpression = 'neutral';
      companionExpressionIntensity = 0;
    } else if (detail.expression && ['neutral', 'curious', 'focused', 'alert'].includes(detail.expression)) {
      companionExpression = detail.expression;
      const intensity = typeof detail.intensity === 'number' && Number.isFinite(detail.intensity)
        ? detail.intensity
        : 0.5;
      companionExpressionIntensity = Math.max(0, Math.min(1, intensity));
    }
    project();
  };
  const unsubscribe = liveConversationStore.subscribe(project);
  const observer = new MutationObserver(project);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener(DESKTOP_COMPANION_EXPRESSION_EVENT, handleExpression);
  project();
  return () => {
    unsubscribe();
    observer.disconnect();
    window.removeEventListener(DESKTOP_COMPANION_EXPRESSION_EVENT, handleExpression);
    companionExpression = 'neutral';
    companionExpressionIntensity = 0;
  };
}
