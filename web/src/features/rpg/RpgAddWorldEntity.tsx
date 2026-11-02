import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { rpgWorldAuthoringClient, type RpgAuthoringTopic } from './api/rpgWorldAuthoringClient';

/**
 * An author adds an entry to a topic (evolution roadmap EV-6): its id, kind and name; the rest is written in its
 * editor once it is there (its gear, home, aliases and group, its dossier).
 */
export function RpgAddWorldEntity({ worldId, topic, label }: { worldId: string; topic: RpgAuthoringTopic; label: string }) {
  const queryClient = useQueryClient();
  const [id, setId] = useState('');
  const [kind, setKind] = useState('');
  const [name, setName] = useState('');
  const [status, setStatus] = useState('');

  const add = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await rpgWorldAuthoringClient.addEntity(worldId, topic.topic_id, {
        expected_draft_revision: topic.draft_revision,
        expected_content_hash: topic.content_hash,
        entity: { id: id.trim(), kind: kind.trim(), name: name.trim() },
      });
      setStatus(`Added ${name.trim()}.`);
      setId('');
      setName('');
      await queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-section', worldId, topic.topic_id] });
    } catch (cause) {
      setStatus(cause instanceof Error ? cause.message : 'The entry could not be added.');
    }
  };

  return (
    <form className="rpg-authoring-add-entity" aria-label={`Add to ${label}`} onSubmit={(event) => void add(event)}>
      <label><span>Id</span><input required value={id} onChange={(event) => setId(event.currentTarget.value)} placeholder="npc:new-person" /></label>
      <label><span>Kind</span><input required value={kind} onChange={(event) => setKind(event.currentTarget.value)} placeholder="npc" /></label>
      <label><span>Name</span><input required value={name} onChange={(event) => setName(event.currentTarget.value)} /></label>
      <button type="submit" disabled={!id.trim() || !kind.trim() || !name.trim()}>Add entry</button>
      {status ? <p role="status">{status}</p> : null}
    </form>
  );
}
