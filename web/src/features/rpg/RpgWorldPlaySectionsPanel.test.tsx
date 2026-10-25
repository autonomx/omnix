import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgWorldPlaySectionsPanel } from './RpgWorldPlaySectionsPanel';
import { createTestQueryClient } from '../../test/renderWithProviders';

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

const DERIVED = { economy: 'derived', routines: 'derived', knowledge: 'derived', pressures: 'derived', bestiary: 'derived' };
const EMPTY = { economy: { providers: [] }, routines: [], knowledge: [], pressures: [], bestiary: [] };
const OFFER = { offer_key: 'room', service: 'lodging', name: 'A room', description: '', price: { gold: 0, silver: 5, copper: 0 },
  item_id: '', stock: 6, restock_per_day: 0 };
const PROVIDER = { provider_id: 'npc:mara', location_id: 'loc:inn', sells: [OFFER], buys: null };

function view(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    world_id: 'world:aurelia',
    document: EMPTY,
    content_hash: 'hash-1',
    saved: false,
    unpublished: false,
    published_revision: 2,
    readiness: { published: DERIVED, draft: DERIVED },
    findings: [],
    references: {
      people: [{ id: 'npc:mara', name: 'Mara Vey' }],
      places: [{ id: 'loc:inn', name: 'The Inn' }],
      items: [], creatures: [], regions: [], quests: [],
    },
    ...overrides,
  };
}

function renderPanel(responses: (url: string, init?: RequestInit) => Response) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    return responses(url, init);
  }));
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <RpgWorldPlaySectionsPanel worldId="world:aurelia" />
    </QueryClientProvider>,
  );
  return calls;
}

describe('RpgWorldPlaySectionsPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('drafts empty sections from the lore, saves with the hash it read, then publishes', async () => {
    const saved = view({ document: { ...EMPTY, economy: { providers: [PROVIDER] } }, content_hash: 'hash-2', saved: true,
      unpublished: true, readiness: { published: DERIVED, draft: { ...DERIVED, economy: 'authored' } } });
    const calls = renderPanel((url, init) => {
      if (url.endsWith('/draft-from-lore')) return jsonResponse({ ok: true, world_id: 'world:aurelia', document: { ...EMPTY, economy: { providers: [PROVIDER] } } });
      if (url.endsWith('/publish')) return jsonResponse({ ...saved, unpublished: false, published_revision: 3, readiness: { published: saved.readiness.draft, draft: saved.readiness.draft } });
      if (init?.method === 'PUT') return jsonResponse(saved);
      return jsonResponse(view());
    });

    expect(await screen.findByRole('heading', { name: 'How It Plays' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Draft empty sections from lore' }));
    expect(await screen.findByText(/World Forge drafted 1 empty section from the lore/)).toBeInTheDocument();
    const offer = screen.getByRole('group', { name: 'Sells' });
    expect(within(offer).getByText('A room')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox').some((select) => (select as HTMLSelectElement).value === 'npc:mara')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByText(/Saved with the world/)).toBeInTheDocument();
    const put = calls.find((call) => call.init?.method === 'PUT');
    expect(JSON.parse(String(put?.init?.body))).toEqual({ expected_content_hash: 'hash-1', document: { ...EMPTY, economy: { providers: [PROVIDER] } } });
    expect(screen.getByText('Saved, not yet published')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));
    expect(await screen.findByText('Published as revision 3. New campaigns play it.')).toBeInTheDocument();
  });

  it('names what the world lacks, in words, and keeps the draft unpublishable', async () => {
    renderPanel(() => jsonResponse(view({ saved: true, unpublished: true, document: { ...EMPTY, routines: [{ npc_id: 'npc:ghost', schedule: [], goals: [] }] },
      findings: ['play_section_unknown_person:routines:npc:ghost'] })));
    expect(await screen.findByText('Routines names a person the world does not have: npc:ghost')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled();
    fireEvent.click(screen.getByRole('tab', { name: /Routines/ }));
    expect(screen.getByRole('option', { name: 'npc:ghost (not in this world)' })).toBeInTheDocument();
  });

  it('shows each error of a wrongly shaped draft, and a newer save made elsewhere', async () => {
    let attempt = 0;
    renderPanel((_url, init) => {
      if (init?.method !== 'PUT') return jsonResponse(view());
      attempt += 1;
      return attempt === 1
        ? jsonResponse({ detail: { ok: false, error: 'world_play_sections_invalid', findings: ['play_section_invalid:economy.providers.0.provider_id:String should have at least 1 character'] } }, 422)
        : jsonResponse({ detail: { ok: false, error: 'world_play_sections_conflict:expected=hash-1:current=hash-9' } }, 409);
    });
    await screen.findByRole('heading', { name: 'How It Plays' });
    fireEvent.click(screen.getByRole('button', { name: 'Add seller' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(await screen.findByText('Not valid: economy.providers.0.provider_id:String should have at least 1 character')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(screen.getByText('A newer draft was saved elsewhere. Reload it before saving again.')).toBeInTheDocument());
  });
});
