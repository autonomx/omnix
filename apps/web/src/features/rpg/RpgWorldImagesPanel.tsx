import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldImageClient,
  type RpgWorldImageTarget,
} from '../../api/rpgWorldImageClient';
import './RpgWorldImagesPanel.css';

interface RpgWorldImagesPanelProps {
  worldId: string;
}

function imageUrl(assetId: string | null | undefined): string | undefined {
  return assetId ? `/api/assets/${encodeURIComponent(assetId)}/file` : undefined;
}

function latestAsset(target: RpgWorldImageTarget): string | undefined {
  return target.attempts.find((attempt) => attempt.asset_id)?.asset_id ?? undefined;
}

function label(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RpgWorldImagesPanel({ worldId }: RpgWorldImagesPanelProps) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [providerId, setProviderId] = useState('');
  const [feedback, setFeedback] = useState('');
  const query = useQuery({
    queryKey: ['feature', 'rpg', 'world-image-targets', worldId],
    queryFn: () => rpgWorldImageClient.list(worldId),
    refetchInterval: 4000,
  });
  const targets = query.data?.targets ?? [];
  const selectedTargets = useMemo(
    () => targets.filter((target) => selected.includes(target.target_id)),
    [selected, targets],
  );

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-image-targets', worldId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-workspace'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
    ]);
  };

  const generate = useMutation({
    mutationFn: () => rpgWorldImageClient.generate(worldId, {
      target_ids: selected,
      prompts: Object.fromEntries(selectedTargets.map((target) => [
        target.target_id,
        prompts[target.target_id] ?? target.suggested_prompt,
      ])),
      provider_id: providerId,
      no_cache: false,
    }),
    onSuccess: async (result) => {
      setFeedback(`Queued ${result.jobs.length} image job${result.jobs.length === 1 ? '' : 's'}.`);
      await refresh();
    },
    onError: (cause) => setFeedback(cause instanceof Error ? cause.message : 'Images could not be queued.'),
  });

  const review = useMutation({
    mutationFn: ({ targetId, reviewState, assetId }: { targetId: string; reviewState: string; assetId?: string }) => (
      rpgWorldImageClient.update(worldId, targetId, {
        review_state: reviewState,
        active_asset_id: assetId,
      })
    ),
    onSuccess: refresh,
    onError: (cause) => setFeedback(cause instanceof Error ? cause.message : 'Image review failed.'),
  });

  const regenerate = useMutation({
    mutationFn: (target: RpgWorldImageTarget) => rpgWorldImageClient.regenerate(
      worldId,
      target.target_id,
      {
        prompt: prompts[target.target_id] ?? target.suggested_prompt,
        provider_id: providerId,
        no_cache: true,
      },
    ),
    onSuccess: async () => {
      setFeedback('A replacement image was queued.');
      await refresh();
    },
    onError: (cause) => setFeedback(cause instanceof Error ? cause.message : 'Image regeneration failed.'),
  });

  return (
    <section className="rpg-authoring-page rpg-world-images-panel" aria-label="World images">
      <div className="rpg-authoring-page-heading">
        <div><p className="eyebrow">Presentation assets</p><h2>Images</h2><p>Generate, review, and assign images independently from canon generation.</p></div>
        <span>{targets.length} target{targets.length === 1 ? '' : 's'}</span>
      </div>
      <div className="rpg-world-images-toolbar">
        <label><span>Provider override</span><input placeholder="Use configured provider" value={providerId} onChange={(event) => setProviderId(event.currentTarget.value)} /></label>
        <button type="button" disabled={!selected.length || generate.isPending} onClick={() => generate.mutate()}>{generate.isPending ? 'Queuing…' : `Generate Selected (${selected.length})`}</button>
        <button className="rpg-secondary-button" type="button" onClick={() => setSelected(targets.filter((target) => ['missing', 'stale', 'failed'].includes(target.status)).map((target) => target.target_id))}>Select Missing &amp; Stale</button>
      </div>
      {feedback ? <p className="rpg-authoring-feedback" aria-live="polite">{feedback}</p> : null}
      {query.isPending ? <p>Discovering image targets…</p> : null}
      {query.isError ? <p className="rpg-world-catalog-error">Unable to load image targets.</p> : null}
      <div className="rpg-world-image-grid">
        {targets.map((target) => {
          const generatedAsset = latestAsset(target);
          const visibleAsset = target.active_asset_id ?? generatedAsset;
          const preview = imageUrl(visibleAsset);
          return (
            <article key={target.target_id}>
              <div className="rpg-world-image-preview" style={preview ? { backgroundImage: `url(${JSON.stringify(preview)})` } : undefined}>
                {!preview ? <span>{target.role.slice(0, 1).toUpperCase()}</span> : null}
                <label><input type="checkbox" checked={selected.includes(target.target_id)} onChange={(event) => setSelected((current) => event.currentTarget.checked ? [...current, target.target_id] : current.filter((value) => value !== target.target_id))} /><span>Select</span></label>
              </div>
              <div className="rpg-world-image-copy">
                <h3>{String(target.metadata.entity_name ?? target.target_id)}</h3>
                <p>{label(target.target_type)} · {label(target.role)}</p>
                <div className="rpg-chip-row"><span>{label(target.status)}</span><span>{label(target.review_state)}</span>{target.active_asset_id ? <span>Active</span> : null}</div>
                <textarea rows={4} value={prompts[target.target_id] ?? target.suggested_prompt} onChange={(event) => setPrompts((current) => ({ ...current, [target.target_id]: event.currentTarget.value }))} />
                <div className="rpg-world-image-actions">
                  <button className="rpg-secondary-button" type="button" disabled={regenerate.isPending} onClick={() => regenerate.mutate(target)}>Regenerate</button>
                  <button type="button" disabled={!generatedAsset || review.isPending} onClick={() => review.mutate({ targetId: target.target_id, reviewState: 'approved', assetId: generatedAsset })}>Approve</button>
                  <button className="rpg-secondary-button" type="button" disabled={review.isPending} onClick={() => review.mutate({ targetId: target.target_id, reviewState: 'rejected' })}>Reject</button>
                </div>
                {target.attempts.length ? <details><summary>Previous images ({target.attempts.length})</summary>{target.attempts.map((attempt) => <div key={attempt.job_id}><span>{label(attempt.status)}</span>{attempt.asset_id ? <a href={imageUrl(attempt.asset_id)} target="_blank" rel="noreferrer">Open image</a> : null}</div>)}</details> : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
