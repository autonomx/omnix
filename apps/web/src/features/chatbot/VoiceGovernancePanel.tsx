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
  { id: 'character', label: 'Link to a character' },
  { id: 'live_call', label: 'Use in live calls' },
  { id: 'system_assistant', label: 'Use for System Assistant' },
  { id: 'general_tts', label: 'Use for general text-to-speech' },
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

  if (!assetId) return <section><h4>Linked voice governance</h4><p>No default voice is linked to this character.</p></section>;
  const current = governanceQuery.data;
  function toggleUse(use: VoiceAllowedUse, enabled: boolean): void {
    const next = enabled ? [...new Set([...draft.allowed_uses, use])] : draft.allowed_uses.filter((item) => item !== use);
    setDraft({ ...draft, allowed_uses: next });
  }

  return <section className="voice-governance-panel">
    <h4>Linked voice governance</h4>
    <p>Consent and provenance are required before this cloned voice can be linked or used for a character call.</p>
    {governanceQuery.isPending ? <p>Loading voice governance…</p> : <>
      <div className="character-form-grid">
        <label>Voice subject / owner<input aria-label="Voice subject owner" value={draft.subject_owner} onChange={(event) => setDraft({ ...draft, subject_owner: event.currentTarget.value })} /></label>
        <label>Creator ID<input aria-label="Voice creator id" value={draft.creator_id} onChange={(event) => setDraft({ ...draft, creator_id: event.currentTarget.value })} /></label>
        <label>Source type<input aria-label="Voice source type" value={draft.source_type} onChange={(event) => setDraft({ ...draft, source_type: event.currentTarget.value })} /></label>
        <label>Source reference<input aria-label="Voice source reference" value={draft.source_reference ?? ''} onChange={(event) => setDraft({ ...draft, source_reference: event.currentTarget.value })} /></label>
        <label>Consent status<select aria-label="Voice consent status" value={draft.consent_status} onChange={(event) => setDraft({ ...draft, consent_status: event.currentTarget.value as VoiceConsentStatus })}><option value="unverified">Unverified</option><option value="granted">Granted</option><option value="revoked">Revoked</option></select></label>
        <label>Deletion state<select aria-label="Voice deletion state" value={draft.deletion_state} onChange={(event) => setDraft({ ...draft, deletion_state: event.currentTarget.value as VoiceDeletionState })}><option value="active">Active</option><option value="pending_deletion">Pending deletion</option><option value="deleted">Deleted</option></select></label>
        <label className="wide">Deletion reason<input aria-label="Voice deletion reason" value={draft.deletion_reason ?? ''} onChange={(event) => setDraft({ ...draft, deletion_reason: event.currentTarget.value })} /></label>
      </div>
      <fieldset className="character-action-options"><legend>Allowed uses</legend>{useOptions.map((option) => <label key={option.id}><input type="checkbox" checked={draft.allowed_uses.includes(option.id)} onChange={(event) => toggleUse(option.id, event.currentTarget.checked)} />{option.label}</label>)}</fieldset>
      <dl className="voice-governance-metadata">
        <div><dt>Asset</dt><dd>{assetId}</dd></div>
        <div><dt>Source SHA-256</dt><dd>{current?.source_sha256 ?? 'Unavailable'}</dd></div>
        <div><dt>Consent recorded</dt><dd>{current?.consent_recorded_at ?? 'Not recorded'}</dd></div>
      </dl>
      <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>Save voice governance</button>
    </>}
    {status ? <p role="status">{status}</p> : null}
  </section>;
}
