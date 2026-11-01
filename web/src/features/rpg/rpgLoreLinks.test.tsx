import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { linkSpans, RpgLinkedText, RpgLoreLinksProvider } from './rpgLoreLinks';
import { RpgLoreEntryPanel } from './RpgLoreEntryPanel';

const LINKABLE = [
  { entry_id: 'npc:liora-fen', family: 'person', names: ['Liora Fen', 'Liora'] },
  { entry_id: 'location:aurelia:starfall-village', family: 'place', names: ['Starfall Village'] },
  { entry_id: 'location:other', family: 'place', names: ['Twin Hollow'] },
  { entry_id: 'location:other-2', family: 'place', names: ['Twin Hollow'] },
];

describe('linkSpans', () => {
  it('links names as written, longest first, and no name two entries share', () => {
    const text = 'Liora Fen waits in Starfall Village; the village and Twin Hollow are quiet. Liora nods.';
    expect(linkSpans(text, LINKABLE).map((span) => [text.slice(span.start, span.end), span.entry_id])).toEqual([
      ['Liora Fen', 'npc:liora-fen'], ['Starfall Village', 'location:aurelia:starfall-village'], ['Liora', 'npc:liora-fen'],
    ]);
  });
});

describe('RpgLinkedText and the lore entry', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('opens a name in the story beside it, by reading only', async () => {
    const methods: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const isRequest = typeof input === 'object' && 'method' in input;
      methods.push((isRequest ? (input as Request).method : init?.method) ?? 'GET');
      const url = decodeURIComponent((isRequest ? (input as Request).url : String(input)).replace(/^https?:\/\/[^/]+/, ''));
      if (url.endsWith('/lore/linkable')) {
        return new Response(JSON.stringify({ ok: true, session_id: 'campaign:test', entries: LINKABLE }), { status: 200 });
      }
      return new Response(JSON.stringify({
        ok: true, session_id: 'campaign:test', entry: {
          entry_id: 'npc:liora-fen', family: 'person', name: 'Liora Fen',
          lore: { role: 'Guide', description: 'She guides new arrivals to Starfall Village.' },
          learned: { known_as: 'met', told: [], facts: [] }, links: { text: '', lore: [] },
        },
      }), { status: 200 });
    }));

    render(
      <RpgLoreLinksProvider sessionId="campaign:test">
        <p><RpgLinkedText spans={[{ entry_id: 'npc:liora-fen', start: 5, end: 14 }]} text="Find Liora Fen." /></p>
        <RpgLoreEntryPanel />
      </RpgLoreLinksProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Liora Fen: open its lore' }));
    const panel = await screen.findByRole('complementary', { name: 'Lore' });
    await waitFor(() => expect(within(panel).getByRole('heading', { name: 'Liora Fen' })).toBeInTheDocument());
    expect(panel).toHaveTextContent('You have met them.');
    await waitFor(() => expect(within(panel).getByRole('button', { name: 'Starfall Village: open its lore' })).toBeInTheDocument());
    expect(methods.every((method) => method === 'GET')).toBe(true);
    fireEvent.click(within(panel).getByRole('button', { name: 'Close the lore' }));
    expect(screen.queryByRole('complementary', { name: 'Lore' })).toBeNull();
  });
});
