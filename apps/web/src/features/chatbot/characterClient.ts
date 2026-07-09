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

export interface CharacterListResponse {
  characters: CharacterProfile[];
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
  greeting: string;
  speech_style: LiveCallSpeechStyle;
  read_memory: boolean;
  write_memory: boolean;
  shared_memory_access: 'none' | 'read_only';
  memory_snapshot_id?: string | null;
  preload: {
    profile_loaded: boolean;
    voice_resolved: boolean;
    memory_snapshot_loaded: boolean;
    memory_record_count: number;
    preload_ms: number;
    resolved_at: string;
  };
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

export const characterClient = {
  list(): Promise<CharacterListResponse> {
    return request('/api/characters');
  },
  session(sessionId: string): Promise<SessionInteraction> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/interaction`);
  },
  liveCallRuntime(sessionId: string): Promise<CharacterLiveCallRuntime> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/live-call/runtime`);
  },
  setSession(
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
    return request(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/interaction`,
      jsonInit('POST', {
        transcript_policy: 'persistent',
        read_memory: false,
        write_memory: false,
        shared_memory_access: 'none',
        ...input,
      }),
    );
  },
};
