import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  characterClient,
  type UpdateVoiceProfileGovernanceInput,
  type VoiceAllowedUse,
  type VoiceConsentStatus,
  type VoiceDeletionState,
} from './characterClient';

const useOptions: Array<{ id: VoiceAllowedUse; label: string }> = [
  { id: 'character', label: 'character' },
  { id: 'live_call', label: 'live_call' },
  { id: 'system_assistant', label: 'system_assistant' },
  { id: 'general_tts', label: 'general_tts' },
];

export function VoiceGovernancePanel({ assetId }: { assetId?: string | null }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<UpdateVoiceProfileGovernanceInput>({
    subject_owner: '', source_type: 'unknown', source_reference: '', creator_id: '',
    consent_status: 'unverified', allowed_uses: [], deletion_state: 'active', deletion_reason: '',
  });
  const [status, setStatus] = useState<string | null>(null);
  const governanceQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'voice-governance', assetId],
    queryFn: () => characterClient.voiceGovernance(assetId ?? ''),
    enabled: Boolean(assetId),
  });

  useEffect(() => {
    const value = governanceQuery.data;
    if (!value) return;
    setDraft({
      subject_owner: value.subject_owner,
      source_type: value.source_type,
      source_reference: value.source_reference,
      creator_id: value.creator_id,
      consent_status: value.consent_status,
      allowed_uses: value.allowed_uses,
      deletion_state: value.deletion_state,
      deletion_reason: value.deletion_reason,
    });
  }, [governanceQuery.data]);

  const mutation = useMutation({
    mutationFn: () => characterClient.updateVoiceGovernance(assetId ?? '', draft),
    onSuccess: async () => {
      setStatus('Voice ownership, consent, and allowed-use metadata saved.');
      await queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'voice-governance', assetId] });
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Voice governance update failed.'),
  });

  function toggleUse(use: VoiceAllowedUse, enabled: boolean): void {
    const next = enabled ? [...new Set([...draft.allowed_uses, use])] : draft.allowed_uses.filter((item) => item !== use);
    setDraft({ ...draft, allowed_uses: next });
  }

  const current = governanceQuery.data;
  const displayName = current?.subject_owner || (assetId ? 'Linked cloned voice' : 'No linked voice');
  const consentReady = current?.consent_status === 'granted' && current.deletion_state === 'active';

  return <section className="character-dashboard-section character-voice-section">
    <header className="character-section-heading">
      <div><span>2</span><h4>Voice governance</h4></div>
    </header>

    {!assetId ? <div className="voice-governance-empty"><span aria-hidden="true">◉</span><div><strong>No default voice linked</strong><p>Link a governed cloned voice before starting a Character Mode live call.</p></div></div> : governanceQuery.isPending ? <p>Loading voice governance…</p> : <>
      <div className="voice-governance-summary">
        <span className="voice-governance-icon" aria-hidden="true">≋</span>
        <div>
          <strong>{displayName}</strong>
          <small>{abbreviateAsset(assetId)}</small>
        </div>
        <span className={consentReady ? 'voice-consent-badge ready' : 'voice-consent-badge'}>
          {consentReady ? 'Consent on file' : current?.consent_status ?? 'Unverified'}
        </span>
      </div>

      <div className="voice-use-summary">
        <small>Allowed uses</small>
        <div>{draft.allowed_uses.length ? draft.allowed_uses.map((use) => <span key={use}>{use}</span>) : <em>No allowed uses</em>}</div>
      </div>

      <details className="voice-governance-details">
        <summary>View / edit consent and provenance</summary>
        <div className="character-form-grid">
          <label>Voice subject / owner<input aria-label="Voice subject owner" value={draft.subject_owner} onChange={(event) => setDraft({ ...draft, subject_owner: event.currentTarget.value })} /></label>
          <label>Creator ID<input aria-label="Voice creator id" value={draft.creator_id} onChange={(event) => setDraft({ ...draft, creator_id: event.currentTarget.value })} /></label>
          <label>Source type<input aria-label="Voice source type" value={draft.source_type} onChange={(event) => setDraft({ ...draft, source_type: event.currentTarget.value })} /></label>
          <label>Source reference<input aria-label="Voice source reference" value={draft.source_reference ?? ''} onChange={(event) => setDraft({ ...draft, source_reference: event.currentTarget.value })} /></label>
          <label>Consent status<select aria-label="Voice consent status" value={draft.consent_status} onChange={(event) => setDraft({ ...draft, consent_status: event.currentTarget.value as VoiceConsentStatus })}><option value="unverified">Unverified</option><option value="granted">Granted</option><option value="revoked">Revoked</option></select></label>
          <label>Deletion state<select aria-label="Voice deletion state" value={draft.deletion_state} onChange={(event) => setDraft({ ...draft, deletion_state: event.currentTarget.value as VoiceDeletionState })}><option value="active">Active</option><option value="pending_deletion">Pending deletion</option><option value="deleted">Deleted</option></select></label>
          <label className="wide">Deletion reason<input aria-label="Voice deletion reason" value={draft.deletion_reason ?? ''} onChange={(event) => setDraft({ ...draft, deletion_reason: event.currentTarget.value })} /></label>
        </div>
        <fieldset className="voice-use-options"><legend>Allowed uses</legend>{useOptions.map((option) => <label key={option.id}><input type="checkbox" checked={draft.allowed_uses.includes(option.id)} onChange={(event) => toggleUse(option.id, event.currentTarget.checked)} />{option.label}</label>)}</fieldset>
        <dl className="voice-governance-metadata">
          <div><dt>Asset</dt><dd>{assetId}</dd></div>
          <div><dt>Source SHA-256</dt><dd>{current?.source_sha256 ?? 'Unavailable'}</dd></div>
          <div><dt>Consent recorded</dt><dd>{current?.consent_recorded_at ?? 'Not recorded'}</dd></div>
        </dl>
        <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>Save voice governance</button>
      </details>
    </>}
    <p className="character-section-note">Voice and consent remain separate resources from the character profile and avatar pack.</p>
    {status ? <p role="status">{status}</p> : null}
  </section>;
}

function abbreviateAsset(assetId: string): string {
  if (assetId.length <= 42) return assetId;
  return `${assetId.slice(0, 22)}…${assetId.slice(-12)}`;
}
