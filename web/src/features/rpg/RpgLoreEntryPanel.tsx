import { useEffect, useRef, useState } from 'react';
import { api } from './api/gateway';
import type { components } from './api/generated';
import { RpgLinkedText, useRpgLoreLinks } from './rpgLoreLinks';
import './RpgLoreEntryPanel.css';

type LoreEntry = components['schemas']['RpgLoreEntryView'];

const LORE_LABELS: Record<string, string> = {
  role: 'Role', description: 'About', appearance: 'Appearance', background: 'Background', region_name: 'Region',
  kind: 'Kind', objective: 'Objective', type: 'Type', rarity: 'Rarity', threat: 'Threat', habitat: 'Habitat',
};
const KNOWN_AS: Record<string, string> = { visited: 'You have been here.', met: 'You have met them.', heard_of: 'You have heard of it.' };

/**
 * The entry a lore link opened (evolution roadmap EV-12), beside the story: its public lore, what the hero has learned
 * of it, and links onward (its lore's names). Reading it changes nothing in the campaign.
 */
export function RpgLoreEntryPanel() {
  const links = useRpgLoreLinks();
  const [entry, setEntry] = useState<LoreEntry | null>(null);
  const [failed, setFailed] = useState(false);
  const heading = useRef<HTMLHeadingElement | null>(null);
  const entryId = links?.openEntryId ?? '';
  const sessionId = links?.sessionId ?? '';

  useEffect(() => {
    let active = true;
    setEntry(null);
    setFailed(false);
    if (!entryId || !sessionId) return () => { active = false; };
    void api.GET('/api/rpg/sessions/{session_id}/lore/entries/{entry_id}', {
      params: { path: { session_id: sessionId, entry_id: entryId } },
    }).then(({ data, error }) => {
      if (!active) return;
      if (error || !data?.entry) setFailed(true);
      else setEntry(data.entry as LoreEntry);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [entryId, sessionId]);

  useEffect(() => {
    if (entry) heading.current?.focus();
  }, [entry]);

  useEffect(() => {
    if (!entryId) return undefined;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') links?.close(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [entryId, links]);

  if (!links || !entryId) return null;
  const learned = entry?.learned;
  return (
    <aside className="rpg-lore-entry" aria-label="Lore">
      <div className="rpg-lore-entry-head">
        <h2 ref={heading} tabIndex={-1}>{entry?.name ?? (failed ? 'Not known' : 'Opening…')}</h2>
        <button className="rpg-lore-entry-close" onClick={links.close} type="button" aria-label="Close the lore">×</button>
      </div>
      {failed ? <p>There is nothing to tell of this yet.</p> : null}
      {entry ? (
        <>
          <dl className="rpg-lore-entry-lore">
            {Object.entries(entry.lore).map(([key, value]) => (
              <div key={key}>
                <dt>{LORE_LABELS[key] ?? key}</dt>
                <dd><RpgLinkedText text={value} /></dd>
              </div>
            ))}
          </dl>
          {learned && (learned.known_as || learned.told.length || learned.facts.length) ? (
            <section className="rpg-lore-entry-learned" aria-label="What you have learned">
              <h3>What you have learned</h3>
              {learned.known_as ? <p>{KNOWN_AS[learned.known_as] ?? learned.known_as}</p> : null}
              {[...learned.told, ...learned.facts].length ? (
                <ul>{[...learned.told, ...learned.facts].map((line) => <li key={line}><RpgLinkedText text={line} /></li>)}</ul>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </aside>
  );
}
