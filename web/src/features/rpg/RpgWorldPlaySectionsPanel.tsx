import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  RpgPlaySectionsError,
  rpgWorldPlaySectionsClient,
  type RpgPlaySectionsDraft,
  type RpgPlaySectionsResponse,
} from './api/rpgWorldPlaySectionsClient';
import { PlaySectionRows } from './RpgPlaySectionForm';
import { PLAY_SECTIONS, describeFinding, type NameOf, type PlaySectionId } from './rpgPlaySectionFields';
import './RpgWorldPlaySections.css';

/**
 * How a world plays, in the world editor (RQ-4.1): its economy, routines, knowledge, pressures, bestiary and quests. The
 * author drafts them (or has World Forge draft them from the lore), saves the draft with the world, and publishes
 * it; a section left empty is inferred from the lore when a campaign starts.
 */

interface RpgWorldPlaySectionsPanelProps {
  worldId: string;
}

const QUERY_KEY = 'rpg-world-play-sections';

function errorText(error: unknown): string {
  if (error instanceof RpgPlaySectionsError) {
    if (error.code.startsWith('world_play_sections_conflict')) return 'A newer draft was saved elsewhere. Reload it before saving again.';
    if (error.code.startsWith('world_play_sections_invalid:')) return 'The world cannot publish this draft: it names what the world does not have.';
    if (error.code.startsWith('world_play_sections_need_a_published_revision')) return 'Publish the world once before drafting from its lore.';
    return error.code || error.message;
  }
  return error instanceof Error ? error.message : 'Something went wrong.';
}

function sourceLabel(source: string | undefined): string {
  return source === 'authored' ? 'Written' : 'From lore';
}

function filledFromLore(current: RpgPlaySectionsDraft, drafted: RpgPlaySectionsDraft): [RpgPlaySectionsDraft, number] {
  let next = current;
  let filled = 0;
  for (const section of PLAY_SECTIONS) {
    if (!section.read(next).length && section.read(drafted).length) {
      next = section.write(next, section.read(drafted));
      filled += 1;
    }
  }
  return [next, filled];
}

export function RpgWorldPlaySectionsPanel({ worldId }: RpgWorldPlaySectionsPanelProps) {
  const queryClient = useQueryClient();
  // A refetch would replace the author's unsaved edits; the page reads again only when it saves or publishes.
  const query = useQuery({ queryKey: [QUERY_KEY, worldId], queryFn: () => rpgWorldPlaySectionsClient.read(worldId), refetchOnWindowFocus: false });
  const view = query.data;
  const [draft, setDraft] = useState<RpgPlaySectionsDraft | null>(null);
  const [active, setActive] = useState<PlaySectionId>('economy');
  const [feedback, setFeedback] = useState('');
  const [invalid, setInvalid] = useState<string[]>([]);
  const [conflict, setConflict] = useState(false);

  useEffect(() => { if (view) setDraft(view.document); }, [view]);

  const name: NameOf = useMemo(() => {
    const names = new Map<string, string>();
    for (const rows of Object.values(view?.references ?? {})) for (const row of rows) names.set(row.id, row.name);
    return (id) => (typeof id === 'string' && id ? names.get(id) ?? id : 'Choose…');
  }, [view]);

  const accept = (next: RpgPlaySectionsResponse, message: string) => {
    queryClient.setQueryData([QUERY_KEY, worldId], next);
    setDraft(next.document);
    setInvalid([]);
    setConflict(false);
    setFeedback(message);
  };
  const fail = (error: unknown) => {
    setInvalid(error instanceof RpgPlaySectionsError ? error.findings : []);
    setConflict(error instanceof RpgPlaySectionsError && error.code.startsWith('world_play_sections_conflict'));
    setFeedback(errorText(error));
  };
  const reload = async () => {
    const fresh = await query.refetch();
    if (fresh.data) accept(fresh.data, 'Reloaded the draft saved with the world.');
  };
  const save = useMutation({
    mutationFn: () => rpgWorldPlaySectionsClient.save(worldId, view?.content_hash ?? '', draft as RpgPlaySectionsDraft),
    onSuccess: (next) => accept(next, 'Saved with the world. Publish it for new campaigns to play it.'),
    onError: fail,
  });
  const publish = useMutation({
    mutationFn: () => rpgWorldPlaySectionsClient.publish(worldId),
    onSuccess: (next) => accept(next, `Published as revision ${next.published_revision ?? ''}. New campaigns play it.`),
    onError: fail,
  });
  const fromLore = useMutation({
    mutationFn: () => rpgWorldPlaySectionsClient.draftFromLore(worldId),
    onSuccess: (drafted) => {
      const [next, filled] = filledFromLore(draft as RpgPlaySectionsDraft, drafted.document);
      setDraft(next);
      setFeedback(filled ? `World Forge drafted ${filled} empty section${filled === 1 ? '' : 's'} from the lore. Review, then save.` : 'Every section already has rows; nothing was drafted.');
    },
    onError: fail,
  });

  if (query.isPending) return <section className="rpg-authoring-page rpg-play-sections" aria-label="How it plays"><p>Loading how this world plays…</p></section>;
  if (query.isError || !view || !draft) return <section className="rpg-authoring-page rpg-play-sections" aria-label="How it plays"><p className="rpg-world-catalog-error">{errorText(query.error)}</p></section>;

  const dirty = JSON.stringify(draft) !== JSON.stringify(view.document);
  const busy = save.isPending || publish.isPending || fromLore.isPending;
  const neverPublished = view.published_revision === null;
  const section = PLAY_SECTIONS.find((candidate) => candidate.id === active) ?? PLAY_SECTIONS[0];
  const context = { refs: view.references, name };
  const status = dirty ? 'Unsaved changes' : view.unpublished ? 'Saved, not yet published' : view.saved ? 'Published' : 'As published';

  return (
    <section className="rpg-authoring-page rpg-play-sections" aria-label="How it plays">
      <div className="rpg-authoring-page-heading">
        <div>
          <p className="eyebrow">Game Master</p>
          <h2>How It Plays</h2>
          <p>Who sells what, where people are through the day, what they know, the pressures the world’s clock moves, how its creatures fight, and what its quests take. A section left empty is inferred from the world’s lore when a campaign starts.</p>
        </div>
        <span>{status}</span>
      </div>
      {neverPublished ? <p className="rpg-authoring-feedback">Publish the world once (World Generation) before writing how it plays.</p> : null}
      {feedback ? <p className="rpg-authoring-feedback" aria-live="polite">{feedback}</p> : null}
      {conflict ? <button className="rpg-secondary-button" type="button" onClick={() => void reload()}>Reload the saved draft</button> : null}

      <div className="rpg-play-toolbar">
        <button className="rpg-secondary-button" disabled={busy || neverPublished} type="button" onClick={() => fromLore.mutate()}>{fromLore.isPending ? 'Drafting…' : 'Draft empty sections from lore'}</button>
        <button className="rpg-secondary-button" disabled={busy || !dirty} type="button" onClick={() => { setDraft(view.document); setInvalid([]); setFeedback(''); }}>Discard changes</button>
        <button className="rpg-primary-button" disabled={busy || !dirty || neverPublished} type="button" onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save draft'}</button>
        <button className="rpg-primary-button" disabled={busy || dirty || !view.unpublished || view.findings.length > 0} type="button" onClick={() => publish.mutate()}>{publish.isPending ? 'Publishing…' : 'Publish'}</button>
      </div>

      {[...invalid, ...view.findings].length ? (
        <ul className="rpg-play-findings" aria-label="What the world cannot publish">
          {invalid.map((finding) => <li key={finding}>{describeFinding(finding, name)}</li>)}
          {view.findings.map((finding) => <li key={finding}>{describeFinding(finding, name)}</li>)}
        </ul>
      ) : null}

      <div className="rpg-play-tabs" role="tablist" aria-label="Sections">
        {PLAY_SECTIONS.map((candidate) => (
          <button aria-selected={candidate.id === section.id} className={candidate.id === section.id ? 'is-active' : ''} key={candidate.id} role="tab" type="button" onClick={() => setActive(candidate.id)}>
            <strong>{candidate.label}</strong>
            <small>{candidate.read(draft).length ? `${candidate.read(draft).length} written` : 'From lore'} · published: {sourceLabel(view.readiness.published?.[candidate.id])}</small>
          </button>
        ))}
      </div>

      <div className="rpg-play-section" role="tabpanel" aria-label={section.label}>
        <p>{section.summary}</p>
        <PlaySectionRows rows={section.read(draft)} spec={section.rows} onChange={(rows) => setDraft(section.write(draft, rows))} context={context} />
      </div>
    </section>
  );
}
