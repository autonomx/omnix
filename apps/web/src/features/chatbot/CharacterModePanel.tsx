import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { characterClient } from './characterClient';
import './CharacterModePanel.css';

export function CharacterModePanel({ sessionId }: { sessionId: string }) {
  const queryClient = useQueryClient();
  const [selectedCharacterId, setSelectedCharacterId] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const charactersQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'characters'],
    queryFn: () => characterClient.list(),
  });
  const interactionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'interaction', sessionId],
    queryFn: () => characterClient.session(sessionId),
  });
  const characters = charactersQuery.data?.characters.filter((item) => item.enabled && item.status === 'active') ?? [];
  const interaction = interactionQuery.data;
  const effectiveSelectedCharacterId = selectedCharacterId || characters[0]?.id || '';
  const activeCharacter = useMemo(
    () => characters.find((item) => item.id === interaction?.character_id),
    [characters, interaction?.character_id],
  );

  useEffect(() => {
    if (interaction?.character_id) setSelectedCharacterId(interaction.character_id);
    else if (!selectedCharacterId && characters[0]) setSelectedCharacterId(characters[0].id);
  }, [characters, interaction?.character_id, selectedCharacterId]);

  const mutation = useMutation({
    mutationFn: (mode: 'system' | 'character') => {
      const characterId = mode === 'character' ? effectiveSelectedCharacterId : null;
      const character = characters.find((item) => item.id === characterId);
      return characterClient.setSession(sessionId, {
        interaction_mode: mode,
        character_id: characterId,
        voice_asset_id: mode === 'character' ? character?.default_voice_asset_id ?? null : null,
      });
    },
    onSuccess: async (next) => {
      setStatus(next.interaction_mode === 'character'
        ? `Talking to ${characters.find((item) => item.id === next.character_id)?.display_name ?? 'character'} · Memory off`
        : 'Switched to System Assistant · Character memory inactive');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'interaction', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'session', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] }),
      ]);
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Character Mode update failed.'),
  });

  const characterMode = interaction?.interaction_mode === 'character';
  return (
    <article className="character-mode-card" aria-label="Character Mode settings">
      <header>
        <div>
          <p className="eyebrow">Identity</p>
          <h3>Character Mode</h3>
          <p>Use a server-owned character personality and linked voice for this Chat.</p>
        </div>
        <span className={characterMode ? 'active' : ''}>
          {characterMode ? `Talking to ${activeCharacter?.display_name ?? 'character'}` : 'System Assistant'}
        </span>
      </header>
      <div className="character-mode-controls">
        <label>
          Character
          <select
            aria-label="Character"
            value={effectiveSelectedCharacterId}
            disabled={!characters.length || mutation.isPending}
            onChange={(event) => setSelectedCharacterId(event.currentTarget.value)}
          >
            {!characters.length ? <option value="">No characters created</option> : null}
            {characters.map((character) => <option key={character.id} value={character.id}>{character.display_name}</option>)}
          </select>
        </label>
        <div className="character-mode-actions">
          <button
            type="button"
            disabled={!effectiveSelectedCharacterId || mutation.isPending || characterMode}
            onClick={() => mutation.mutate('character')}
          >
            Enable Character Mode
          </button>
          <button
            type="button"
            disabled={mutation.isPending || !characterMode}
            onClick={() => mutation.mutate('system')}
          >
            Use System Assistant
          </button>
        </div>
      </div>
      {activeCharacter ? (
        <dl className="character-mode-details">
          <div><dt>Voice</dt><dd>{activeCharacter.default_voice_asset_id ?? 'Current system voice'}</dd></div>
          <div><dt>Profile version</dt><dd>{activeCharacter.active_version}</dd></div>
          <div><dt>Memory</dt><dd>Off in CHAR-3</dd></div>
        </dl>
      ) : null}
      {status ? <p className="character-mode-status" role="status">{status}</p> : null}
    </article>
  );
}
