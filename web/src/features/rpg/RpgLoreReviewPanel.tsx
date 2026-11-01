import { useCallback, useEffect, useState } from 'react';
import { api } from './api/gateway';
import type { components } from './api/generated';
import './RpgLoreReviewPanel.css';

type Draft = components['schemas']['RpgLoreDraft'];
type DraftGroup = components['schemas']['RpgLoreDraftGroup'];
type ReviewResponse = components['schemas']['RpgLoreReviewResponse'];

const FAMILY: Record<string, string> = { person: 'Person', place: 'Place', item: 'Thing', creature: 'Creature', quest: 'Quest' };

function provenance(draft: Draft): string {
  const from = draft.provenance as { campaign_id?: string; turn?: number; reason?: string };
  return [from.campaign_id ? `campaign ${from.campaign_id}` : '', from.turn !== undefined ? `turn ${from.turn}` : '',
    from.reason ? `“${from.reason}”` : ''].filter(Boolean).join(' · ');
}

/**
 * The world's review queue (evolution roadmap EV-0 part 2, EV-6): what the game master invented in campaigns on this
 * world, grouped by name. Each draft shows where it came from and the consistency check's findings (evidence, not a
 * verdict); the author approves it into the world's next publication, rejects it, or links it to one approved.
 */
export function RpgLoreReviewPanel({ worldId }: { worldId: string }) {
  const [groups, setGroups] = useState<DraftGroup[]>([]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(0);

  const load = useCallback(async () => {
    const { data } = await api.GET('/api/rpg/worlds/{world_id}/lore-review', { params: { path: { world_id: worldId } } });
    setGroups(((data as ReviewResponse | undefined)?.groups ?? []) as DraftGroup[]);
  }, [worldId]);

  useEffect(() => {
    void load().catch(() => setStatus('The review queue could not be loaded.'));
  }, [load]);

  const act = async (draft: Draft, action: 'check' | 'approve' | 'reject' | 'link', linkTo?: number) => {
    setBusy(draft.id);
    try {
      const path = { world_id: worldId, draft_id: draft.id };
      const { error } = action === 'check'
        ? await api.POST('/api/rpg/worlds/{world_id}/lore-review/{draft_id}/check', { params: { path } })
        : await api.POST('/api/rpg/worlds/{world_id}/lore-review/{draft_id}/decision', {
          params: { path }, body: { decision: action, ...(linkTo ? { link_to: linkTo } : {}) },
        });
      setStatus(error ? `${draft.name} could not be ${action === 'check' ? 'checked' : 'decided'}.`
        : action === 'check' ? `${draft.name} checked.` : `${draft.name}: ${action === 'approve' ? 'approved' : action === 'link' ? 'linked' : 'rejected'}.`);
      await load();
    } finally {
      setBusy(0);
    }
  };

  return (
    <section className="rpg-lore-review" aria-labelledby="rpg-lore-review-title">
      <h2 id="rpg-lore-review-title">Inventions to review</h2>
      <p>What the game master invented in campaigns on this world. An approved entry joins the world, with its play data, at its next publication.</p>
      {status ? <p role="status">{status}</p> : null}
      {groups.length ? null : <p>Nothing is waiting for review.</p>}
      {groups.map((group) => {
        const approved = group.drafts.find((row) => row.status === 'approved');
        return (
          <article className="rpg-lore-review-group" key={group.group_key} aria-label={group.group_key}>
            {group.drafts.map((draft) => (
              <div className="rpg-lore-review-draft" key={draft.id}>
                <h3>{draft.name} <span className="rpg-lore-review-family">{FAMILY[draft.family] ?? draft.family}</span></h3>
                <p className="rpg-lore-review-from">{provenance(draft)}</p>
                {typeof draft.entry?.row === 'object' && (draft.entry.row as { description?: string }).description
                  ? <p>{(draft.entry.row as { description?: string }).description}</p> : null}
                {draft.findings && Array.isArray((draft.findings as { findings?: unknown[] }).findings) ? (
                  <ul aria-label={`Findings on ${draft.name}`}>
                    {((draft.findings as { findings: Array<{ kind: string; detail: string }> }).findings).map((finding, index) => (
                      <li key={index}><strong>{finding.kind}:</strong> {finding.detail}</li>
                    ))}
                  </ul>
                ) : null}
                <p className="rpg-lore-review-status">Status: {draft.status}{draft.canon_id ? ` (${draft.canon_id})` : ''}</p>
                {draft.status === 'pending' ? (
                  <div className="rpg-lore-review-actions">
                    <button disabled={busy === draft.id} type="button" onClick={() => void act(draft, 'check')}>Check consistency</button>
                    <button disabled={busy === draft.id} type="button" onClick={() => void act(draft, 'approve')}>Approve</button>
                    {approved && approved.id !== draft.id ? (
                      <button disabled={busy === draft.id} type="button" onClick={() => void act(draft, 'link', approved.id)}>Link to {approved.name}</button>
                    ) : null}
                    <button disabled={busy === draft.id} type="button" onClick={() => void act(draft, 'reject')}>Reject</button>
                  </div>
                ) : null}
              </div>
            ))}
          </article>
        );
      })}
    </section>
  );
}
