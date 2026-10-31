/**
 * Names that open their lore (evolution roadmap EV-12). A turn's response carries the links of its final text; the
 * journal, the quest log and older turns are linked here from the names of what the hero may be shown, by the
 * engine's rule (a name as it is written, shared by no other entry). A link opens the lore panel beside the story:
 * no turn, no model call, nothing changed.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from './api/gateway';
import type { components } from './api/generated';

export type RpgLoreSpan = components['schemas']['RpgLoreLink'];
type Linkable = components['schemas']['RpgLoreLinkable'];

interface LoreLinksValue {
  sessionId: string;
  linkable: Linkable[];
  openEntryId: string;
  open: (entryId: string) => void;
  close: () => void;
}

const LoreLinksContext = createContext<LoreLinksValue | null>(null);

function escaped(name: string): string {
  return name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** The links of `text` by the names of `linkable`: longest first, as written, none overlapping, none shared. */
export function linkSpans(text: string, linkable: Linkable[]): RpgLoreSpan[] {
  const byName = new Map<string, Set<string>>();
  for (const entry of linkable) {
    for (const name of entry.names) {
      if (!/^\p{Lu}/u.test(name)) continue;
      byName.set(name, (byName.get(name) ?? new Set()).add(entry.entry_id));
    }
  }
  const found: RpgLoreSpan[] = [];
  for (const name of [...byName.keys()].sort((a, b) => b.length - a.length)) {
    const ids = byName.get(name);
    if (!ids || ids.size !== 1) continue;
    const pattern = new RegExp(`(?<![\\p{L}\\p{N}_'])${escaped(name)}(?![\\p{L}\\p{N}_'])`, 'gu');
    for (const match of text.matchAll(pattern)) {
      const start = match.index ?? 0;
      const end = start + name.length;
      if (found.some((span) => start < span.end && end > span.start)) continue;
      found.push({ entry_id: [...ids][0], start, end });
    }
  }
  return found.sort((a, b) => a.start - b.start);
}

/** A span the engine counts in characters (code points), counted as the page's strings are (UTF-16 units). */
function utf16Span(text: string, span: RpgLoreSpan): RpgLoreSpan {
  const points = Array.from(text);
  const at = (index: number) => points.slice(0, index).join('').length;
  return { ...span, start: at(span.start), end: at(span.end) };
}

export function RpgLoreLinksProvider({ sessionId, children }: { sessionId: string; children: ReactNode }) {
  const [linkable, setLinkable] = useState<Linkable[]>([]);
  const [openEntryId, setOpenEntryId] = useState('');
  useEffect(() => {
    let active = true;
    setLinkable([]);
    setOpenEntryId('');
    if (!sessionId) return () => { active = false; };
    void api.GET('/api/rpg/sessions/{session_id}/lore/linkable', { params: { path: { session_id: sessionId } } })
      .then(({ data }) => { if (active) setLinkable((data?.entries ?? []) as Linkable[]); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [sessionId]);
  const open = useCallback((entryId: string) => setOpenEntryId(entryId), []);
  const close = useCallback(() => setOpenEntryId(''), []);
  const value = useMemo(() => ({ sessionId, linkable, openEntryId, open, close }), [sessionId, linkable, openEntryId, open, close]);
  return <LoreLinksContext.Provider value={value}>{children}</LoreLinksContext.Provider>;
}

export function useRpgLoreLinks(): LoreLinksValue | null {
  return useContext(LoreLinksContext);
}

/** `text`, its names that open their lore as buttons: the spans given (a turn's), else found by name. */
export function RpgLinkedText({ text, spans }: { text: string; spans?: RpgLoreSpan[] }) {
  const links = useRpgLoreLinks();
  const marks = useMemo(() => {
    if (!links) return [];
    const valid = (spans ?? []).map((span) => utf16Span(text, span))
      .filter((span) => span.start >= 0 && span.end <= text.length && span.start < span.end);
    return valid.length ? valid : linkSpans(text, links.linkable);
  }, [links, spans, text]);
  if (!links || !marks.length) return <>{text}</>;
  const parts: ReactNode[] = [];
  let at = 0;
  for (const [index, span] of marks.entries()) {
    if (span.start < at) continue;
    if (span.start > at) parts.push(text.slice(at, span.start));
    const words = text.slice(span.start, span.end);
    parts.push(
      <button className="rpg-lore-link" key={`${span.entry_id}:${index}`} onClick={() => links.open(span.entry_id)}
        type="button" aria-label={`${words}: open its lore`}>
        {words}
      </button>,
    );
    at = span.end;
  }
  if (at < text.length) parts.push(text.slice(at));
  return <>{parts}</>;
}
