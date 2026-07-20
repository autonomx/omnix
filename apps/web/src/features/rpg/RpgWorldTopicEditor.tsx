import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldAuthoringClient,
  type RpgAuthoringTopic,
} from '../../api/rpgWorldAuthoringClient';

interface RpgWorldTopicEditorProps {
  topic: RpgAuthoringTopic;
  worldId: string;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function RpgWorldTopicEditor({ topic, worldId }: RpgWorldTopicEditorProps) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [contentJson, setContentJson] = useState(JSON.stringify(topic.content, null, 2));
  const authoring = record(record(topic.provenance).authoring);
  const [generationLock, setGenerationLock] = useState(Boolean(authoring.generation_lock));
  const [approved, setApproved] = useState(Boolean(authoring.approved_at));
  const [error, setError] = useState('');

  useEffect(() => {
    setContentJson(JSON.stringify(topic.content, null, 2));
    const nextAuthoring = record(record(topic.provenance).authoring);
    setGenerationLock(Boolean(nextAuthoring.generation_lock));
    setApproved(Boolean(nextAuthoring.approved_at));
  }, [topic]);

  const detailQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-authoring-topic', worldId, topic.topic_id],
    queryFn: () => rpgWorldAuthoringClient.topic(worldId, topic.topic_id),
    enabled: isEditing,
  });
  const current = detailQuery.data?.topic ?? topic;
  const history = detailQuery.data?.history ?? [];

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-topic', worldId, topic.topic_id] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-section', worldId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      const content = JSON.parse(contentJson) as Record<string, unknown>;
      return rpgWorldAuthoringClient.updateTopic(worldId, topic.topic_id, {
        expected_draft_revision: current.draft_revision,
        expected_content_hash: current.content_hash,
        content,
        generation_lock: generationLock,
        approved,
      });
    },
    onSuccess: async () => {
      setError('');
      setIsEditing(false);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Topic could not be saved.'),
  });

  const restoreMutation = useMutation({
    mutationFn: (historySequence: number) => rpgWorldAuthoringClient.restoreTopic(
      worldId,
      topic.topic_id,
      {
        expected_draft_revision: current.draft_revision,
        expected_content_hash: current.content_hash,
        history_sequence: historySequence,
      },
    ),
    onSuccess: async () => {
      setError('');
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Topic could not be restored.'),
  });

  const state = useMemo(() => {
    const currentAuthoring = record(record(current.provenance).authoring);
    if (currentAuthoring.generation_lock) return 'Locked from bulk generation';
    if (currentAuthoring.approved_at) return 'Approved';
    return current.source === 'manual' ? 'Manually edited' : 'Generated';
  }, [current]);

  return (
    <section className="rpg-authoring-topic-editor" aria-label="Topic editing and history">
      <div className="rpg-authoring-page-heading">
        <div><h3>Topic controls</h3><p>{state} · {current.content_hash.slice(0, 18)}…</p></div>
        <button className="rpg-secondary-button" type="button" onClick={() => setIsEditing((value) => !value)}>
          {isEditing ? 'Close Editor' : 'Edit Topic'}
        </button>
      </div>
      {error ? <p className="rpg-world-catalog-error">{error}</p> : null}
      {isEditing ? (
        <div className="rpg-authoring-topic-editor-grid">
          <form onSubmit={(event) => { event.preventDefault(); saveMutation.mutate(); }}>
            <label><span>Structured topic JSON</span><textarea rows={20} value={contentJson} onChange={(event) => setContentJson(event.currentTarget.value)} /></label>
            <label className="rpg-authoring-checkbox"><input type="checkbox" checked={generationLock} onChange={(event) => setGenerationLock(event.currentTarget.checked)} /><span>Lock from automatic generation</span></label>
            <label className="rpg-authoring-checkbox"><input type="checkbox" checked={approved} onChange={(event) => setApproved(event.currentTarget.checked)} /><span>Mark reviewed and approved</span></label>
            <button type="submit" disabled={saveMutation.isPending || detailQuery.isPending}>{saveMutation.isPending ? 'Saving…' : 'Save Topic'}</button>
            <small>Saving requires the current draft revision and content hash. Concurrent changes are rejected.</small>
          </form>
          <section>
            <h4>Topic history</h4>
            {detailQuery.isPending ? <p>Loading history…</p> : null}
            {history.map((entry) => (
              <article key={entry.history_sequence}>
                <div><strong>Revision {entry.draft_revision}</strong><p>{entry.source} · {entry.status} · {new Date(entry.captured_at).toLocaleString()}</p><small>{entry.content_hash.slice(0, 22)}…</small></div>
                <button className="rpg-secondary-button" type="button" disabled={restoreMutation.isPending} onClick={() => restoreMutation.mutate(entry.history_sequence)}>Restore</button>
              </article>
            ))}
            {!detailQuery.isPending && !history.length ? <p>No previous versions are recorded yet.</p> : null}
          </section>
        </div>
      ) : null}
    </section>
  );
}
