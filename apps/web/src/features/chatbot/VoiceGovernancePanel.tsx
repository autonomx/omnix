import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { characterClient, type CharacterProfile } from './characterClient';

export function VoiceGovernancePanel({
  assetId,
  character,
  characterIsActive = false,
  activationPending = false,
  onActivateCharacter,
}: {
  assetId?: string | null;
  character?: CharacterProfile;
  characterIsActive?: boolean;
  activationPending?: boolean;
  onActivateCharacter?: () => void;
}) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<string | null>(null);
  const [selectedVoiceId, setSelectedVoiceId] = useState(assetId ?? '');
  const voiceAssetsQuery = useQuery({
    queryKey: ['platform', 'assets', 'character-voice-selector'],
    queryFn: () => omnixApiClient.listAssets(),
    enabled: Boolean(character),
  });

  useEffect(() => {
    setSelectedVoiceId(assetId ?? '');
  }, [assetId]);

  const assignmentMutation = useMutation({
    mutationFn: () => characterClient.update(character?.id ?? '', {
      expected_version: character?.active_version,
      default_voice_asset_id: selectedVoiceId,
    }),
    onSuccess: async (updated) => {
      setStatus(`${voiceLabel(selectedVoiceId)} is now ${updated.display_name}'s live-call voice.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'characters'] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'interaction'] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'live-call-runtime'] }),
      ]);
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Character voice assignment failed.'),
  });

  const clonedVoices = (voiceAssetsQuery.data?.assets ?? []).filter(isClonedVoice);
  const selectedVoiceIsCurrent = Boolean(selectedVoiceId) && selectedVoiceId === assetId;

  return <section className="character-dashboard-section character-voice-section">
    <header className="character-section-heading">
      <div><span>2</span><h4>Voice governance</h4></div>
    </header>

    {character ? <div className="character-voice-assignment">
      <label>
        <span>Character live-call voice</span>
        <select aria-label="Character live-call voice" value={selectedVoiceId} onChange={(event) => setSelectedVoiceId(event.currentTarget.value)}>
          <option value="">Select a cloned voice</option>
          {clonedVoices.map((voice) => <option key={voice.id} value={voice.id}>{voiceLabel(voice.id, voice.metadata)}</option>)}
        </select>
      </label>
      <button
        type="button"
        className={selectedVoiceIsCurrent ? 'current' : undefined}
        disabled={!selectedVoiceId || selectedVoiceIsCurrent || assignmentMutation.isPending}
        title={selectedVoiceIsCurrent ? `${voiceLabel(selectedVoiceId)} is already used for this character's live calls.` : undefined}
        onClick={() => assignmentMutation.mutate()}
      >
        {assignmentMutation.isPending
          ? 'Assigning…'
          : selectedVoiceIsCurrent
            ? 'Currently used for live calls'
            : 'Use for character live calls'}
      </button>
    </div> : null}

    {character && onActivateCharacter ? <div className="character-live-activation">
      <div>
        <strong>{characterIsActive ? `${character.display_name} is active in Live Voice` : `Use ${character.display_name} in Live Voice`}</strong>
        <small>{characterIsActive ? 'The live-call identity, linked voice, and avatar come from this character.' : 'Switch the current chat from System Assistant to this character, including its linked voice and avatar.'}</small>
      </div>
      <button
        type="button"
        className={characterIsActive ? 'current' : undefined}
        disabled={characterIsActive || activationPending}
        onClick={onActivateCharacter}
      >
        {activationPending ? 'Activating…' : characterIsActive ? 'Active in Live Voice' : `Use ${character.display_name}`}
      </button>
    </div> : null}

    {!assetId ? <div className="voice-governance-empty"><span aria-hidden="true">◉</span><div><strong>No default voice is linked to this character.</strong><p>Link a cloned voice before starting a Character Mode live call.</p></div></div> : <div className="voice-governance-summary">
      <span className="voice-governance-icon" aria-hidden="true">≋</span>
      <div>
        <strong>{voiceLabel(assetId)}</strong>
        <small>{abbreviateAsset(assetId)}</small>
      </div>
      <span className="voice-consent-badge ready">Ready for use</span>
    </div>}
    <p className="character-section-note">All cloned voices are automatically available for characters, live calls, System Assistant, and text-to-speech.</p>
    {status ? <p role="status">{status}</p> : null}
  </section>;
}

function abbreviateAsset(assetId: string): string {
  if (assetId.length <= 42) return assetId;
  return `${assetId.slice(0, 22)}…${assetId.slice(-12)}`;
}

function isClonedVoice(asset: { module: string; type: string }): boolean {
  return asset.module === 'voice-cloning' && asset.type === 'voice_profile';
}

function voiceLabel(assetId: string, metadata?: Record<string, unknown>): string {
  const metadataLabel = String(metadata?.voice_clone_id || metadata?.voice_id || '').trim();
  return metadataLabel || assetId.replace(/^voice-cloning:/, '').replaceAll('-', ' ');
}
