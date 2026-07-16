import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { rpgWorldLibraryClient } from '../../api/rpgWorldLibraryClient';
import './RpgStarterBubblePromotionPanel.css';

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function RpgStarterBubblePromotionPanel() {
  const queryClient = useQueryClient();
  const [worldId, setWorldId] = useState('');
  const [sourceRevision, setSourceRevision] = useState(1);
  const [startingLocation, setStartingLocation] = useState('rusty_flagon_tavern');
  const [neighboringLocation, setNeighboringLocation] = useState('northern_road');
  const [preview, setPreview] = useState<Record<string, unknown>>();
  const [feedback, setFeedback] = useState<string>();
  const [error, setError] = useState<string>();

  const libraryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library'],
    queryFn: () => rpgWorldLibraryClient.list(),
  });
  const detailQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library', worldId],
    queryFn: () => rpgWorldLibraryClient.detail(worldId),
    enabled: Boolean(worldId),
  });

  useEffect(() => {
    const firstWorld = libraryQuery.data?.worlds[0];
    if (!worldId && firstWorld) setWorldId(firstWorld.id);
  }, [libraryQuery.data, worldId]);

  useEffect(() => {
    const latestRevision = detailQuery.data?.revisions[0]?.revision;
    if (latestRevision) setSourceRevision(latestRevision);
  }, [detailQuery.data]);

  const previewMutation = useMutation({
    mutationFn: () => rpgWorldLibraryClient.previewStarterBubble(
      worldId,
      sourceRevision,
      startingLocation,
      neighboringLocation || undefined,
    ),
    onSuccess: (result) => {
      setPreview(result);
      setFeedback('Starter bubble preview is ready. No world revision was changed.');
      setError(undefined);
    },
    onError: (cause) => {
      setError(cause instanceof Error ? cause.message : 'Starter bubble preview failed.');
      setFeedback(undefined);
    },
  });

  const promoteMutation = useMutation({
    mutationFn: () => rpgWorldLibraryClient.promoteStarterBubble(worldId, {
      source_world_revision: sourceRevision,
      starting_location_id: startingLocation,
      neighboring_location_id: neighboringLocation || undefined,
    }),
    onSuccess: async (result) => {
      const promotion = record(result.promotion);
      setFeedback(
        `Promoted to world revision ${String(promotion.world_revision ?? '?')} / release ${String(promotion.world_release ?? '?')}.`,
      );
      setError(undefined);
      await queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-library'] });
    },
    onError: (cause) => {
      setError(cause instanceof Error ? cause.message : 'Starter bubble promotion failed.');
      setFeedback(undefined);
    },
  });

  const previewPlan = record(preview?.starter_bubble);
  const previewSlots = list(previewPlan.slots);
  const predictiveJobs = list(preview?.predictive_materialization);

  return (
    <details className="rpg-starter-bubble-panel">
      <summary>
        <span>
          <strong>Starter bubble promotion</strong>
          <small>Preview region, settlement, interior, neighbor, and deferred maps.</small>
        </span>
      </summary>
      <div className="rpg-starter-bubble-panel-body">
        <div className="rpg-starter-bubble-controls">
          <label>
            <span>World</span>
            <select value={worldId} onChange={(event) => setWorldId(event.currentTarget.value)}>
              <option value="">Select a world</option>
              {(libraryQuery.data?.worlds ?? []).map((world) => (
                <option value={world.id} key={world.id}>{world.title}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Source revision</span>
            <select value={sourceRevision} onChange={(event) => setSourceRevision(Number(event.currentTarget.value))}>
              {(detailQuery.data?.revisions ?? []).map((revision) => (
                <option value={revision.revision} key={revision.revision}>Revision {revision.revision}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Starting settlement</span>
            <input value={startingLocation} onChange={(event) => setStartingLocation(event.currentTarget.value)} />
          </label>
          <label>
            <span>Neighboring location</span>
            <input value={neighboringLocation} onChange={(event) => setNeighboringLocation(event.currentTarget.value)} />
          </label>
        </div>
        <div className="rpg-starter-bubble-actions">
          <button
            type="button"
            disabled={!worldId || !sourceRevision || previewMutation.isPending}
            onClick={() => previewMutation.mutate()}
          >
            Preview starter bubble
          </button>
          <button
            type="button"
            disabled={!worldId || !sourceRevision || promoteMutation.isPending}
            onClick={() => promoteMutation.mutate()}
          >
            Promote to future revision
          </button>
        </div>
        {feedback ? <p className="rpg-starter-bubble-feedback" aria-live="polite">{feedback}</p> : null}
        {error ? <p className="rpg-starter-bubble-error" aria-live="assertive">{error}</p> : null}
        {preview ? (
          <div className="rpg-starter-bubble-preview">
            <div>
              <strong>{previewSlots.length} planned locations</strong>
              <span>Simulation and presentation readiness are tracked separately.</span>
            </div>
            <div>
              <strong>{predictiveJobs.length} predictive jobs</strong>
              <span>Optional art remains non-blocking; navigable placeholders are authoritative.</span>
            </div>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
          </div>
        ) : null}
      </div>
    </details>
  );
}
