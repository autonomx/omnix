import {
  readLiveConversationSettings,
  updateLiveConversationSettings,
} from '../assistant-workspace/live-voice-conversation-settings';

export type PresencePreset = 'quiet' | 'natural' | 'engaged' | 'listener';
export type ConversationStance = 'automatic' | 'listen' | 'discuss' | 'advise' | 'brainstorm' | 'teach';
export type ConversationPace = 'quick' | 'balanced' | 'reflective';
export type InterruptionPreference = 'easy' | 'balanced' | 'finish_more';
export type AssistantBackchannelMode = 'off' | 'minimal' | 'natural';
export type InitiativeMode = 'off' | 'gentle' | 'active';
export type LongPauseBehavior = 'wait' | 'reassure' | 'ask_to_continue';
export type ResponseLength = 'brief' | 'conversational' | 'detailed';
export type ResponseOnsetStyle = 'adaptive' | 'immediate' | 'natural' | 'reflective';
export type EmotionalAttunement = 'off' | 'subtle' | 'expressive';
export type TopicContinuity = 'focused' | 'natural' | 'exploratory';
export type DuplexMode = 'automatic' | 'half_duplex' | 'echo_aware';
export type PronunciationSavePolicy = 'ask' | 'session_only' | 'allow';

export type LiveConversationProfile = {
  presence_preset: PresencePreset;
  talkativeness: number;
  conversation_stance: ConversationStance;
  conversation_pace: ConversationPace;
  interruption_preference: InterruptionPreference;
  assistant_backchannel_mode: AssistantBackchannelMode;
  initiative_mode: InitiativeMode;
  idle_threshold_ms: number;
  long_pause_behavior: LongPauseBehavior;
  response_length: ResponseLength;
  response_onset_style: ResponseOnsetStyle;
  emotional_attunement: EmotionalAttunement;
  topic_continuity: TopicContinuity;
  max_idle_prompts: number;
  duplex_mode: DuplexMode;
  pronunciation_save_policy: PronunciationSavePolicy;
  profile_version: number;
};

export type LiveConversationProfileEnvelope = {
  user_defaults: LiveConversationProfile;
  session_override: LiveConversationProfile | null;
  effective: LiveConversationProfile;
  source: 'user_defaults' | 'session_override';
};

export type LiveConversationProfilePatch = Partial<Omit<LiveConversationProfile, 'profile_version'>>;

export const LIVE_CONVERSATION_PROFILE_CHANGED_EVENT = 'omnix:live-conversation-profile-changed';
export const LIVE_CONVERSATION_EFFECTIVE_PROFILE_KEY = 'omnix.liveConversation.effectiveProfile';
const MIGRATION_KEY = 'omnix.liveConversation.serverProfileMigrated.v1';
const CANONICAL_LEGACY_KEY = 'omnix.liveConversation.settings';
const ASSISTANT_LEGACY_KEY = 'omnix.chatbot.assistantSettings';

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) throw new Error(`Live Chat profile request failed with status ${response.status}.`);
  return response.json() as Promise<T>;
}

export const liveConversationProfileClient = {
  defaults: () => requestJson<LiveConversationProfile>('/api/live-chat/profile/defaults'),
  updateDefaults: (patch: LiveConversationProfilePatch) => requestJson<LiveConversationProfile>(
    '/api/live-chat/profile/defaults',
    { method: 'PATCH', body: JSON.stringify(patch) },
  ),
  get: (sessionId: string) => requestJson<LiveConversationProfileEnvelope>(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-conversation/profile`,
  ),
  update: (sessionId: string, patch: LiveConversationProfilePatch) => requestJson<LiveConversationProfileEnvelope>(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-conversation/profile`,
    { method: 'PATCH', body: JSON.stringify(patch) },
  ),
  clear: (sessionId: string) => requestJson<LiveConversationProfileEnvelope>(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-conversation/profile`,
    { method: 'DELETE' },
  ),
};

export function mirrorProfileForLegacyRuntime(profile: LiveConversationProfile): void {
  updateLiveConversationSettings({
    conversationPace: profile.conversation_pace,
    interruptionPreference: profile.interruption_preference,
    backchannelMode: profile.assistant_backchannel_mode,
  });
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LIVE_CONVERSATION_EFFECTIVE_PROFILE_KEY, JSON.stringify(profile));
  } catch {
    // The in-memory event remains available when storage is blocked.
  }
  window.dispatchEvent(new CustomEvent<LiveConversationProfile>(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, {
    detail: profile,
  }));
}

export function readEffectiveLiveConversationProfile(): LiveConversationProfile | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LIVE_CONVERSATION_EFFECTIVE_PROFILE_KEY);
    return raw ? JSON.parse(raw) as LiveConversationProfile : null;
  } catch {
    return null;
  }
}

export async function migrateLegacyConversationSettingsOnce(): Promise<boolean> {
  if (typeof window === 'undefined' || window.localStorage.getItem(MIGRATION_KEY) === 'done') return false;
  const hasLegacySettings = window.localStorage.getItem(CANONICAL_LEGACY_KEY) !== null
    || window.localStorage.getItem(ASSISTANT_LEGACY_KEY) !== null;
  if (!hasLegacySettings) {
    window.localStorage.setItem(MIGRATION_KEY, 'done');
    return false;
  }
  const legacy = readLiveConversationSettings();
  await liveConversationProfileClient.updateDefaults({
    conversation_pace: legacy.conversationPace,
    interruption_preference: legacy.interruptionPreference,
    assistant_backchannel_mode: legacy.backchannelMode,
  });
  window.localStorage.setItem(MIGRATION_KEY, 'done');
  return true;
}
