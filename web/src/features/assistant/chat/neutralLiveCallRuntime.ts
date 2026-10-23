import type { CharacterLiveCallRuntime, LiveCallSpeechStyle } from './characterClient';

/** The runtime of a new system session whose runtime endpoint is unavailable: no character, memory or avatar. */
export function neutralSystemLiveCallRuntime(sessionId: string, voiceAssetId: string | null, speechStyle: LiveCallSpeechStyle): CharacterLiveCallRuntime {
  return {
    session_id: sessionId,
    interaction_mode: 'system',
    display_name: 'System Assistant',
    character_id: null,
    character_profile_version: null,
    effective_identity_hash: null,
    voice_asset_id: voiceAssetId,
    voice_speaker_id: null,
    avatar_pack: null,
    greeting: '',
    speech_style: speechStyle,
    read_memory: false,
    write_memory: false,
    shared_memory_access: 'none',
    memory_snapshot_id: null,
    preload: {
      profile_loaded: false,
      voice_resolved: Boolean(voiceAssetId),
      voice_error: null,
      avatar_pack_loaded: false,
      memory_snapshot_loaded: false,
      memory_record_count: 0,
      preload_ms: 0,
      resolved_at: new Date().toISOString(),
    },
  };
}

/** The speech style a runtime has before the server's (the TTS defaults). */
export const NEUTRAL_SPEECH_STYLE: LiveCallSpeechStyle = {
  speed: 1,
  temperature: 0.6,
  top_k: 20,
  top_p: 0.85,
  repetition_penalty: 1,
  expressiveness: 'neutral',
  emotion: 'neutral',
  interruption_style: 'balanced',
};
