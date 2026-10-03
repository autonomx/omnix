import {
  liveChatEvaluationClient,
  type PresencePolicyVersion,
  type PresencePreset,
} from './live-chat-evaluation-client';
import { liveConversationStore } from './live-conversation-store';

let livePresencePolicyInstalled = false;

export const LIVE_PRESENCE_POLICY_REFRESH_EVENT = 'omnix:live-presence-policy-refresh';
const PERF_EVENT = 'omnix:assistant-voice-perf';

let policies: Partial<Record<PresencePreset, PresencePolicyVersion>> = {};
let refreshGeneration = 0;
let projectedPreset: PresencePreset | null = null;

export function initializeLivePresencePolicyController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  if (livePresencePolicyInstalled) return () => undefined;
  livePresencePolicyInstalled = true;

  const handleRefresh = () => { void refreshPresencePolicies(); };
  const unsubscribe = liveConversationStore.subscribe(projectCurrentPresencePolicy);
  window.addEventListener(LIVE_PRESENCE_POLICY_REFRESH_EVENT, handleRefresh);
  projectCurrentPresencePolicy();
  void refreshPresencePolicies();

  return () => {
    refreshGeneration += 1;
    unsubscribe();
    window.removeEventListener(LIVE_PRESENCE_POLICY_REFRESH_EVENT, handleRefresh);
    policies = {};
    projectedPreset = null;
    liveConversationStore.dispatch({ type: 'presence_policy', policy: null });
    livePresencePolicyInstalled = false;
  };
}

export async function refreshPresencePolicies(): Promise<void> {
  const generation = ++refreshGeneration;
  try {
    const next = await liveChatEvaluationClient.activePolicies();
    if (generation !== refreshGeneration) return;
    policies = next;
    projectedPreset = null;
    projectCurrentPresencePolicy();
    dispatchPerf('presence_policy_loaded', {
      presets: Object.keys(next),
      selected_version: liveConversationStore.getState().presencePolicy?.version ?? null,
    });
  } catch (error) {
    if (generation !== refreshGeneration) return;
    dispatchPerf('presence_policy_load_failed', {
      error_name: error instanceof Error ? error.name : 'unknown',
    });
  }
}

export function projectCurrentPresencePolicy(): PresencePolicyVersion | null {
  const runtime = liveConversationStore.getState();
  const preset = runtime.profile?.presence_preset ?? null;
  const policy = preset ? policies[preset] ?? null : null;
  if (preset === projectedPreset && runtime.presencePolicy === policy) return policy;
  projectedPreset = preset;
  if (runtime.presencePolicy !== policy) {
    liveConversationStore.dispatch({ type: 'presence_policy', policy });
  }
  return policy;
}

function dispatchPerf(stage: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}
