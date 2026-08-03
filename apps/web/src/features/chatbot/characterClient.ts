import { applyAvatarPackToCurrentRuntime, publishCharacterAvatarRuntime } from './liveCharacterAvatarBridge';
import './liveCharacterVisemeBridge';
import './live2dCharacterRenderer';

export type CharacterAvatarRenderMode = 'audio_envelope' | 'viseme' | 'static';
export type CharacterAvatarRenderer = 'sprite' | 'live2d' | 'rive';

export interface CharacterAvatarPack {
  character_id: string;
  version: number;
  render_mode: CharacterAvatarRenderMode;
  renderer: CharacterAvatarRenderer;
  rig_asset_id?: string | null;
  base_asset_id?: string | null;
  mouth_frames: Record<string, string>;
  blink_frames: Record<string, string>;
  expression_frames: Record<string, string>;
  outfit_frames: Record<string, string>;
  background_asset_ids: Record<string, string>;
  active_outfit?: string | null;
  active_background?: string | null;
  mouth_anchor: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface UpsertCharacterAvatarPackInput {
  expected_version?: number | null;
  render_mode?: CharacterAvatarRenderMode;
  renderer?: CharacterAvatarRenderer;
  rig_asset_id?: string | null;
  base_asset_id?: string | null;
  mouth_frames?: Record<string, string>;
  blink_frames?: Record<string, string>;
  expression_frames?: Record<string, string>;
  outfit_frames?: Record<string, string>;
  background_asset_ids?: Record<string, string>;
  active_outfit?: string | null;
  active_background?: string | null;
  mouth_anchor?: Record<string, number>;
}

export interface CharacterProfile {
  id: string;
  display_name: string;
  description: string;
  personality_prompt: string;
  default_greeting: string;
  default_voice_asset_id?: string | null;
  speech_style: Record<string, unknown>;
  identity_policy: Record<string, unknown>;
  shared_memory_policy: Record<string, unknown>;
  active_version: number;
  enabled: boolean;
  status: 'active' | 'archived';
  created_at: string;
  updated_at: string;
}

export interface CharacterListResponse { characters: CharacterProfile[]; }

export type VoiceConsentStatus = 'unverified' | 'granted' | 'revoked';
export type VoiceDeletionState = 'active' | 'pending_deletion' | 'deleted';
export type VoiceAllowedUse = 'character' | 'live_call' | 'system_assistant' | 'general_tts';

export interface VoiceProfileGovernance {
  asset_id: string;
  subject_owner: string;
  source_type: string;
  source_reference: string;
  creator_id: string;
  consent_status: VoiceConsentStatus;
  consent_recorded_at?: string | null;
  allowed_uses: VoiceAllowedUse[];
  source_sha256?: string | null;
  deletion_state: VoiceDeletionState;
  deletion_requested_at?: string | null;
  deleted_at?: string | null;
  deletion_reason: string;
  updated_at: string;
}

export interface UpdateVoiceProfileGovernanceInput {
  subject_owner: string;
  source_type: string;
  source_reference?: string;
  creator_id: string;
  consent_status: VoiceConsentStatus;
  allowed_uses: VoiceAllowedUse[];
  deletion_state: VoiceDeletionState;
  deletion_reason?: string;
}

export interface SessionInteraction {
  id: string;
  title: string;
  interaction_mode: 'system' | 'character';
  character_id?: string | null;
  voice_asset_id?: string | null;
  read_memory: boolean;
  write_memory: boolean;
  shared_memory_access: 'none' | 'read_only';
  transcript_policy: 'persistent' | 'temporary' | 'none';
  character_profile_version?: number | null;
  effective_identity_hash?: string | null;
  messages: Array<{ id: string; role: string; content: string; created_at: string }>;
}

export interface LiveCallSpeechStyle {
  speed: number;
  temperature: number;
  top_k: number;
  top_p: number;
  repetition_penalty: number;
  expressiveness: string;
  emotion: string;
  interruption_style: string;
}

export interface CharacterLiveCallRuntime {
  session_id: string;
  interaction_mode: 'system' | 'character';
  display_name: string;
  character_id?: string | null;
  character_profile_version?: number | null;
  effective_identity_hash?: string | null;
  voice_asset_id?: string | null;
  voice_speaker_id?: string | null;
  voice_profile_asset_id?: string | null;
  greeting: string;
  avatar_pack?: CharacterAvatarPack | null;
  speech_style: LiveCallSpeechStyle;
  read_memory: boolean;
  write_memory: boolean;
  shared_memory_access: 'none' | 'read_only';
  memory_snapshot_id?: string | null;
  preload: {
    profile_loaded: boolean;
    voice_resolved: boolean;
    voice_error?: string | null;
    avatar_pack_loaded?: boolean;
    memory_snapshot_loaded: boolean;
    memory_record_count: number;
    preload_ms: number;
    resolved_at: string;
  };
}

export interface CharacterDataExport {
  character: CharacterProfile;
  versions: Array<{ character_id: string; version: number; personality_prompt: string; created_at: string }>;
  memories: Array<{ id: string; category: string; scope: string; content: string; pinned: boolean; revision: number }>;
  pending_suggestions: Array<{ id: string; proposed_category: string; proposed_content: string; confidence: number; created_at: string }>;
  sessions: Array<{ id: string; title: string; message_count: number; character_message_count: number; created_at: string; updated_at: string }>;
  generated_at: string;
}

export interface CharacterDataActionResponse {
  ok: boolean;
  character_id: string;
  deleted_memory_records: number;
  deleted_memory_candidates: number;
  deleted_memory_snapshots: number;
  deleted_transcript_messages: number;
  voice_unlinked: boolean;
  profile_archived: boolean;
}

const LIVE_CALL_RUNTIME_CACHE_TTL_MS = 5 * 60_000;
const trackedPlaybackRuntimes = new Map<string, Set<CharacterLiveCallRuntime>>();
const liveCallRuntimeCache = new Map<string, { runtime: CharacterLiveCallRuntime; cachedAt: number }>();
const liveCallRuntimeRequests = new Map<string, Promise<CharacterLiveCallRuntime>>();
let latestTrustedPlaybackRuntime: CharacterLiveCallRuntime | null = null;

export function readLatestTrustedCharacterRuntime(): CharacterLiveCallRuntime | null {
  return latestTrustedPlaybackRuntime;
}

export function applyCharacterAvatarPackToTrackedRuntimes(
  characterId: string,
  avatarPack: CharacterAvatarPack | null,
): void {
  let runtimeToPublish: CharacterLiveCallRuntime | null = null;
  for (const tracked of trackedPlaybackRuntimes.values()) {
    for (const runtime of tracked) {
      if (runtime.character_id !== characterId) continue;
      runtime.avatar_pack = avatarPack;
      if (runtime === latestTrustedPlaybackRuntime) runtimeToPublish = runtime;
    }
  }
  if (latestTrustedPlaybackRuntime?.character_id === characterId) {
    latestTrustedPlaybackRuntime.avatar_pack = avatarPack;
    runtimeToPublish = latestTrustedPlaybackRuntime;
  }
  if (runtimeToPublish) publishCharacterAvatarRuntime(runtimeToPublish);
  else applyAvatarPackToCurrentRuntime(characterId, avatarPack);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Character request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function adaptLiveCallRuntimeForPlayback(runtime: CharacterLiveCallRuntime): CharacterLiveCallRuntime {
  const speakerId = runtime.voice_speaker_id?.trim();
  if (!speakerId) return runtime;
  return {
    ...runtime,
    voice_profile_asset_id: runtime.voice_asset_id ?? null,
    voice_asset_id: speakerId,
  };
}

function synchronizeTrackedPlaybackRuntime(runtime: CharacterLiveCallRuntime): CharacterLiveCallRuntime {
  const playbackRuntime = adaptLiveCallRuntimeForPlayback(runtime);
  const tracked = trackedPlaybackRuntimes.get(playbackRuntime.session_id) ?? new Set<CharacterLiveCallRuntime>();
  const incomingPackVersion = playbackRuntime.avatar_pack?.version ?? -1;
  const newerTrackedPack = [...tracked].find((existing) => (
    existing.character_id === playbackRuntime.character_id
    && (existing.avatar_pack?.version ?? -1) > incomingPackVersion
  ))?.avatar_pack;

  // Avatar selection updates the active runtime immediately. A runtime request
  // that began before that mutation can finish afterwards with the previous
  // pack, so never let an older pack version put the old Live2D rig back on
  // screen.
  if (newerTrackedPack) playbackRuntime.avatar_pack = newerTrackedPack;
  for (const existing of tracked) Object.assign(existing, playbackRuntime);
  tracked.add(playbackRuntime);
  trackedPlaybackRuntimes.set(playbackRuntime.session_id, tracked);
  liveCallRuntimeCache.set(playbackRuntime.session_id, {
    runtime: playbackRuntime,
    cachedAt: Date.now(),
  });
  latestTrustedPlaybackRuntime = playbackRuntime;
  publishCharacterAvatarRuntime(playbackRuntime);
  return playbackRuntime;
}

function cachedLiveCallRuntime(sessionId: string): CharacterLiveCallRuntime | null {
  const cached = liveCallRuntimeCache.get(sessionId);
  if (!cached) return null;
  if (Date.now() - cached.cachedAt > LIVE_CALL_RUNTIME_CACHE_TTL_MS) {
    liveCallRuntimeCache.delete(sessionId);
    return null;
  }
  latestTrustedPlaybackRuntime = cached.runtime;
  publishCharacterAvatarRuntime(cached.runtime);
  return cached.runtime;
}

async function loadLiveCallRuntime(
  sessionId: string,
  { force = false }: { force?: boolean } = {},
): Promise<CharacterLiveCallRuntime> {
  if (!force) {
    const cached = cachedLiveCallRuntime(sessionId);
    if (cached) return cached;
    const pending = liveCallRuntimeRequests.get(sessionId);
    if (pending) return pending;
  }

  const pending = request<CharacterLiveCallRuntime>(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-call/runtime`,
  ).then(synchronizeTrackedPlaybackRuntime);
  if (!force) liveCallRuntimeRequests.set(sessionId, pending);
  try {
    return await pending;
  } finally {
    if (!force && liveCallRuntimeRequests.get(sessionId) === pending) {
      liveCallRuntimeRequests.delete(sessionId);
    }
  }
}

function invalidateLiveCallRuntime(sessionId: string): void {
  liveCallRuntimeCache.delete(sessionId);
  liveCallRuntimeRequests.delete(sessionId);
}

export const characterClient = {
  list(includeArchived = false): Promise<CharacterListResponse> {
    return request(`/api/characters${includeArchived ? '?include_archived=true' : ''}`);
  },
  create(input: Pick<CharacterProfile, 'display_name' | 'personality_prompt'> & Partial<CharacterProfile>): Promise<CharacterProfile> {
    return request('/api/characters', jsonInit('POST', input));
  },
  update(characterId: string, input: Record<string, unknown>): Promise<CharacterProfile> {
    return request(`/api/characters/${encodeURIComponent(characterId)}`, jsonInit('PATCH', input));
  },
  data(characterId: string): Promise<CharacterDataExport> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/data`);
  },
  applyDataActions(
    characterId: string,
    input: {
      confirm_character_id: string;
      delete_memories?: boolean;
      delete_transcripts?: boolean;
      unlink_voice?: boolean;
      archive_profile?: boolean;
    },
  ): Promise<CharacterDataActionResponse> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/data/actions`, jsonInit('POST', input));
  },
  avatarPack(characterId: string): Promise<CharacterAvatarPack> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/avatar-pack`);
  },
  upsertAvatarPack(characterId: string, input: UpsertCharacterAvatarPackInput): Promise<CharacterAvatarPack> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/avatar-pack`, jsonInit('PUT', input));
  },
  deleteAvatarPack(characterId: string): Promise<{ ok: boolean; character_id: string }> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/avatar-pack`, { method: 'DELETE' });
  },
  voiceGovernance(assetId: string): Promise<VoiceProfileGovernance> {
    return request(`/api/voice-profiles/${encodeURIComponent(assetId)}/governance`);
  },
  updateVoiceGovernance(
    assetId: string,
    input: UpdateVoiceProfileGovernanceInput,
  ): Promise<VoiceProfileGovernance> {
    return request(
      `/api/voice-profiles/${encodeURIComponent(assetId)}/governance`,
      jsonInit('PATCH', input),
    );
  },
  session(sessionId: string): Promise<SessionInteraction> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/interaction`);
  },
  liveCallRuntime(sessionId: string): Promise<CharacterLiveCallRuntime> {
    return loadLiveCallRuntime(sessionId);
  },
  refreshLiveCallRuntime(sessionId: string): Promise<CharacterLiveCallRuntime> {
    return loadLiveCallRuntime(sessionId, { force: true });
  },
  async setSession(
    sessionId: string,
    input: {
      interaction_mode: 'system' | 'character';
      character_id?: string | null;
      voice_asset_id?: string | null;
      read_memory?: boolean;
      write_memory?: boolean;
      shared_memory_access?: 'none' | 'read_only';
      transcript_policy?: 'persistent' | 'temporary' | 'none';
      continue_topic?: boolean;
    },
  ): Promise<SessionInteraction> {
    const interaction = await request<SessionInteraction>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/interaction`,
      jsonInit('POST', {
        transcript_policy: 'persistent',
        read_memory: false,
        write_memory: false,
        shared_memory_access: 'none',
        ...input,
      }),
    );
    invalidateLiveCallRuntime(sessionId);
    return interaction;
  },
};
