import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldAuthoringClient,
  type RpgAuthoringEntityCard,
  type RpgAuthoringTopic,
} from '../../api/rpgWorldAuthoringClient';

interface RpgWorldEntityEditorProps {
  entity: RpgAuthoringEntityCard;
  topic: RpgAuthoringTopic;
  worldId: string;
}

function parseObject(value: string, label: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function operationLabel(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RpgWorldEntityEditor({ entity, topic, worldId }: RpgWorldEntityEditorProps) {
  const queryClient = useQueryClient();
  const initialEntity = JSON.stringify(entity.metadata, null, 2);
  const [open, setOpen] = useState(false);
  const [rawEntity, setRawEntity] = useState(initialEntity);
  const rawEntityRef = useRef(initialEntity);
  const [entityDraftDirty, setEntityDraftDirty] = useState(false);
  const [rawDirectives, setRawDirectives] = useState('{}');
  const [feedback, setFeedback] = useState('');
  const queryKey = ['feature', 'rpg', 'world-entity', worldId, topic.topic_id, entity.id];
  const entityQuery = useQuery({
    queryKey,
    queryFn: () => rpgWorldAuthoringClient.entity(worldId, topic.topic_id, entity.id),
    enabled: open,
  });

  const replaceDraft = (value: string) => {
    rawEntityRef.current = value;
    setRawEntity(value);
  };

  useEffect(() => {
    if (entityDraftDirty) return;
    const current = entityQuery.data?.entity ?? entity.metadata;
    replaceDraft(JSON.stringify(current, null, 2));
  }, [entity.metadata, entityDraftDirty, entityQuery.data?.entity]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-section', worldId, topic.topic_id] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-image-targets', worldId] }),
    ]);
  };

  const save = useMutation({
    mutationFn: () => rpgWorldAuthoringClient.updateEntity(
      worldId,
      topic.topic_id,
      entity.id,
      {
        expected_draft_revision: topic.draft_revision,
        expected_content_hash: topic.content_hash,
        changes: parseObject(rawEntityRef.current, 'Entity'),
      },
    ),
    onSuccess: async (result) => {
      setEntityDraftDirty(false);
      replaceDraft(JSON.stringify(result.entity, null, 2));
      setFeedback(`Saved ${entity.title}. ${result.stale_entity_ids.length} dependent entities need review.`);
      await refresh();
    },
    onError: (cause) => setFeedback(cause instanceof Error ? cause.message : 'Entity could not be saved.'),
  });

  const regenerate = useMutation({
    mutationFn: () => rpgWorldAuthoringClient.regenerateEntity(
      worldId,
      topic.topic_id,
      entity.id,
      {
        expected_draft_revision: topic.draft_revision,
        expected_content_hash: topic.content_hash,
        directives: parseObject(rawDirectives, 'Regeneration directives'),
      },
    ),
    onSuccess: async (result) => {
      setEntityDraftDirty(false);
      setFeedback(`Regenerated ${entity.title} while preserving ${Math.max(0, ((topic.content.entities as unknown[]) ?? []).length - 1)} sibling entities.`);
      replaceDraft(JSON.stringify(result.entity, null, 2));
      await refresh();
    },
    onError: (cause) => setFeedback(cause instanceof Error ? cause.message : 'Entity could not be regenerated.'),
  });

  return (
    <details
      className="rpg-authoring-entity-editor"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Edit or regenerate</summary>
      <div className="rpg-authoring-entity-editor-body">
        {entityQuery.isPending ? <p>Loading entity history…</p> : null}
        {entityQuery.isError ? <p className="rpg-world-catalog-error">Unable to load entity history.</p> : null}
        <label>
          <span>Structured entity JSON</span>
          <textarea
            aria-label={`Entity JSON for ${entity.title}`}
            rows={14}
            value={rawEntity}
            onChange={(event) => {
              setEntityDraftDirty(true);
              replaceDraft(event.currentTarget.value);
            }}
          />
        </label>
        <div className="rpg-authoring-entity-editor-actions">
          <button type="button" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : 'Save Entity'}
          </button>
        </div>
        <label>
          <span>Regeneration directives</span>
          <textarea
            aria-label={`Regeneration directives for ${entity.title}`}
            rows={5}
            value={rawDirectives}
            onChange={(event) => setRawDirectives(event.currentTarget.value)}
            placeholder={'{"focus":"Deepen motives without changing identity"}'}
          />
        </label>
        <button
          className="rpg-secondary-button"
          type="button"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate()}
        >
          {regenerate.isPending ? 'Regenerating…' : 'Regenerate This Entity'}
        </button>
        {feedback ? <p className="rpg-authoring-feedback" aria-live="polite">{feedback}</p> : null}
        {entityQuery.data?.history.length ? (
          <details className="rpg-authoring-entity-history">
            <summary>Entity history ({entityQuery.data.history.length})</summary>
            {entityQuery.data.history.map((entry) => (
              <article key={entry.history_sequence}>
                <strong>{operationLabel(entry.operation)}</strong>
                <time>{new Date(entry.created_at).toLocaleString()}</time>
                <details><summary>Previous entity</summary><pre>{JSON.stringify(entry.before, null, 2)}</pre></details>
              </article>
            ))}
          </details>
        ) : null}
      </div>
    </details>
  );
}
