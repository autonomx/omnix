import { createLiveCallTraceId } from './live-call-diagnostics-client';
import {
  resolveCharacterPlaybackVoiceDecision,
  type CharacterPlaybackVoiceDecision,
} from './runtime-config';

export type PlaybackVoiceResolution = {
  voiceId: string | null;
  source: string;
  traceId: string;
  diagnosticSource: string;
  details: Record<string, unknown>;
};

type LocalVoiceSetting = {
  voiceId: string | null;
  parseError: boolean;
};

export function resolvePlaybackVoiceWithDiagnostics(caller: string): PlaybackVoiceResolution {
  const safeCaller = caller.trim() || 'unknown-playback';
  const characterDecision = resolveCharacterPlaybackVoiceDecision();
  const mountedVoiceId = document
    .querySelector<HTMLSelectElement>('select[aria-label="Cloned voice"]')
    ?.value.trim() || null;
  const localSetting = readLocalVoiceSetting();

  const voiceId = characterDecision.voiceId ?? mountedVoiceId ?? localSetting.voiceId;
  const source = characterDecision.voiceId
    ? characterDecision.source
    : mountedVoiceId
      ? 'cloned_voice_selector'
      : localSetting.voiceId
        ? 'assistant_settings_local_storage'
        : 'none';
  const traceId = createLiveCallTraceId(`voice-resolution:${safeCaller}`);

  return {
    voiceId,
    source,
    traceId,
    diagnosticSource: safeCaller,
    details: {
      caller: safeCaller,
      final_voice_id: voiceId,
      final_source: source,
      mounted_cloned_voice_id: mountedVoiceId,
      local_storage_voice_id: localSetting.voiceId,
      local_storage_parse_error: localSetting.parseError,
      character_voice_id: characterDecision.voiceId,
      character_voice_source: characterDecision.source,
      character_voice_reason: characterDecision.reason,
      character_decision: characterDecisionForLog(characterDecision),
    },
  };
}

function characterDecisionForLog(decision: CharacterPlaybackVoiceDecision): Record<string, unknown> {
  return {
    card_count: decision.cardCount,
    rendered_identities: decision.renderedIdentities,
    rendered_voice_ids: decision.renderedVoiceIds,
    system_only_rendered: decision.systemOnlyRendered,
    same_selected_session: decision.sameSelectedSession,
    same_displayed_character: decision.sameDisplayedCharacter,
    store_session_id: decision.store.sessionId,
    store_character_id: decision.store.characterId,
    store_display_name: decision.store.displayName,
    store_voice_id: decision.store.voiceId,
    store_profile_version: decision.store.profileVersion,
    runtime_session_id: decision.runtime?.sessionId ?? null,
    runtime_interaction_mode: decision.runtime?.interactionMode ?? null,
    runtime_character_id: decision.runtime?.characterId ?? null,
    runtime_display_name: decision.runtime?.displayName ?? null,
    runtime_voice_asset_id: decision.runtime?.voiceAssetId ?? null,
    runtime_voice_profile_asset_id: decision.runtime?.voiceProfileAssetId ?? null,
    runtime_voice_speaker_id: decision.runtime?.voiceSpeakerId ?? null,
    runtime_voice_resolved: decision.runtime?.voiceResolved ?? false,
    runtime_voice_error: decision.runtime?.voiceError ?? null,
  };
}

function readLocalVoiceSetting(): LocalVoiceSetting {
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem('omnix.chatbot.assistantSettings') || '{}',
    ) as { voiceId?: unknown };
    const voiceId = typeof parsed.voiceId === 'string' ? parsed.voiceId.trim() : '';
    return { voiceId: voiceId || null, parseError: false };
  } catch {
    return { voiceId: null, parseError: true };
  }
}
