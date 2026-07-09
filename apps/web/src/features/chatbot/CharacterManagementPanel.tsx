import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { characterClient, type CharacterDataExport, type CharacterProfile } from './characterClient';
import { VoiceGovernancePanel } from './VoiceGovernancePanel';
import './CharacterManagementPanel.css';

export function CharacterManagementPanel() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState({ display_name: '', description: '', personality_prompt: '', default_greeting: '' });
  const [confirmation, setConfirmation] = useState('');
  const [actions, setActions] = useState({ delete_memories: false, delete_transcripts: false, unlink_voice: false, archive_profile: false });
  const [status, setStatus] = useState<string | null>(null);

  const charactersQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'characters', 'management'],
    queryFn: () => characterClient.list(true),
  });
  const characters = charactersQuery.data?.characters ?? [];
  const selected = characters.find((item) => item.id === selectedId) ?? characters[0];
  const dataQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'character-data', selected?.id],
    queryFn: () => characterClient.data(selected?.id ?? ''),
    enabled: Boolean(selected?.id),
  });

  useEffect(() => {
    if (!selectedId && characters[0]) setSelectedId(characters[0].id);
  }, [characters, selectedId]);

  useEffect(() => {
    if (!selected) return;
    setDraft({
      display_name: selected.display_name,
      description: selected.description,
      personality_prompt: selected.personality_prompt,
      default_greeting: selected.default_greeting,
    });
    setConfirmation('');
    setActions({ delete_memories: false, delete_transcripts: false, unlink_voice: false, archive_profile: false });
  }, [selected?.id, selected?.active_version]);

  async function refresh(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'characters'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'character-data'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'interaction'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'memory'] }),
    ]);
  }

  const createMutation = useMutation({
    mutationFn: () => characterClient.create({
      display_name: 'New Character',
      personality_prompt: 'Be clear, warm, and consistent with this character profile.',
      description: '',
      default_greeting: 'Hello.',
    }),
    onSuccess: async (created) => { setSelectedId(created.id); setStatus('Character created.'); await refresh(); },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Character creation failed.'),
  });

  const updateMutation = useMutation({
    mutationFn: () => characterClient.update(selected?.id ?? '', {
      expected_version: selected?.active_version,
      ...draft,
    }),
    onSuccess: async () => { setStatus('Character profile saved as a new version.'); await refresh(); },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Character update failed.'),
  });

  const actionMutation = useMutation({
    mutationFn: () => characterClient.applyDataActions(selected?.id ?? '', {
      confirm_character_id: confirmation,
      ...actions,
    }),
    onSuccess: async (result) => {
      setStatus(`Character data updated: ${result.deleted_memory_records} memories, ${result.deleted_transcript_messages} transcript messages removed.`);
      setConfirmation('');
      await refresh();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Character data action failed.'),
  });

  function exportData(data: CharacterDataExport): void {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${data.character.id}-character-export.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus('Character export prepared from current backend state.');
  }

  const hasAction = Object.values(actions).some(Boolean);
  return (
    <article className="character-management-card" aria-label="Character management">
      <header>
        <div><p className="eyebrow">Characters</p><h3>Profiles and relationship data</h3><p>Edit versioned profiles, inspect owned data, export it, or perform explicit cleanup.</p></div>
        <button type="button" disabled={createMutation.isPending} onClick={() => createMutation.mutate()}>New character</button>
      </header>

      {charactersQuery.isPending ? <p>Loading characters…</p> : characters.length ? (
        <div className="character-management-layout">
          <nav aria-label="Character profiles">
            {characters.map((character) => (
              <button type="button" className={character.id === selected?.id ? 'active' : undefined} key={character.id} onClick={() => setSelectedId(character.id)}>
                <strong>{character.display_name}</strong>
                <span>{character.status} · v{character.active_version}</span>
              </button>
            ))}
          </nav>

          {selected ? <div className="character-management-editor">
            <section>
              <h4>Profile</h4>
              <div className="character-form-grid">
                <label>Name<input aria-label="Character name" value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.currentTarget.value })} /></label>
                <label>Description<input aria-label="Character description" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.currentTarget.value })} /></label>
                <label className="wide">Personality<textarea aria-label="Character personality" rows={5} value={draft.personality_prompt} onChange={(event) => setDraft({ ...draft, personality_prompt: event.currentTarget.value })} /></label>
                <label className="wide">Greeting<textarea aria-label="Character greeting" rows={2} value={draft.default_greeting} onChange={(event) => setDraft({ ...draft, default_greeting: event.currentTarget.value })} /></label>
              </div>
              <button type="button" disabled={updateMutation.isPending || selected.status === 'archived'} onClick={() => updateMutation.mutate()}>Save new profile version</button>
            </section>

            <VoiceGovernancePanel assetId={selected.default_voice_asset_id} />
            <CharacterDataSummary data={dataQuery.data} loading={dataQuery.isPending} />

            <section className="character-danger-zone">
              <h4>Independent data actions</h4>
              <p>Choose only the data to remove. The cloned voice, profile, memories, and transcripts are separate resources.</p>
              <div className="character-action-options">
                <label><input type="checkbox" checked={actions.delete_memories} onChange={(event) => setActions({ ...actions, delete_memories: event.currentTarget.checked })} />Delete character memories and pending suggestions</label>
                <label><input type="checkbox" checked={actions.delete_transcripts} onChange={(event) => setActions({ ...actions, delete_transcripts: event.currentTarget.checked })} />Delete character transcript messages</label>
                <label><input type="checkbox" checked={actions.unlink_voice} onChange={(event) => setActions({ ...actions, unlink_voice: event.currentTarget.checked })} />Unlink the default voice without deleting it</label>
                <label><input type="checkbox" checked={actions.archive_profile} onChange={(event) => setActions({ ...actions, archive_profile: event.currentTarget.checked })} />Archive the character profile</label>
              </div>
              <label>Type <code>{selected.id}</code> to confirm<input aria-label="Confirm character id" value={confirmation} onChange={(event) => setConfirmation(event.currentTarget.value)} /></label>
              <div className="character-management-actions">
                <button type="button" disabled={!dataQuery.data} onClick={() => dataQuery.data && exportData(dataQuery.data)}>Export character data</button>
                <button type="button" className="danger" disabled={!hasAction || confirmation !== selected.id || actionMutation.isPending} onClick={() => actionMutation.mutate()}>Apply selected actions</button>
              </div>
            </section>
          </div> : null}
        </div>
      ) : <p>No characters have been created.</p>}
      {status ? <p role="status">{status}</p> : null}
    </article>
  );
}

function CharacterDataSummary({ data, loading }: { data?: CharacterDataExport; loading: boolean }) {
  if (loading) return <section><h4>Owned data</h4><p>Loading backend state…</p></section>;
  if (!data) return <section><h4>Owned data</h4><p>Character data is unavailable.</p></section>;
  return <section>
    <h4>Owned data</h4>
    <div className="character-data-metrics">
      <span><strong>{data.versions.length}</strong> profile versions</span>
      <span><strong>{data.memories.length}</strong> memories</span>
      <span><strong>{data.pending_suggestions.length}</strong> pending suggestions</span>
      <span><strong>{data.sessions.reduce((total, item) => total + item.character_message_count, 0)}</strong> transcript messages</span>
    </div>
    {data.memories.length ? <details open><summary>Character memories</summary><ul>{data.memories.map((memory) => <li key={memory.id}><strong>{memory.category}</strong> · <span>{memory.content}</span></li>)}</ul></details> : null}
    {data.pending_suggestions.length ? <details open><summary>Pending suggestions</summary><ul>{data.pending_suggestions.map((candidate) => <li key={candidate.id}><strong>{candidate.proposed_category}</strong> · <span>{candidate.proposed_content}</span></li>)}</ul></details> : null}
  </section>;
}
