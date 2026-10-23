import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../test/renderWithProviders';
import { RpgCommunityWorlds } from './RpgCommunityWorlds';
import { RpgSharedWorldAdoptDialog } from './RpgSharedWorldAdoptDialog';
import { RpgWorldAuthoringWorkspace } from './RpgWorldAuthoringWorkspace';

const SHA = 'a'.repeat(64);

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

const entry = {
  id: 'aurelia',
  version: 1,
  title: 'Aurelia: Echoes Beyond the Gate',
  summary: 'A gate opens between worlds.',
  genre: 'fantasy',
  tone: 'heroic',
  author: 'someone',
  published_at: '2026-10-23',
  bundle: { url: 'https://github.com/autonomx/omnix-worlds/releases/download/t/a.zip', sha256: SHA, bytes: 89344 },
  has_cover: true,
  installed: null,
};

const sharedWorld = {
  id: 'world:aurelia',
  title: 'Aurelia: Echoes Beyond the Gate',
  description: 'A gate opens between worlds.',
  status: 'published',
  source_mode: 'manual',
  genre: 'fantasy',
  tone: 'heroic',
  seed: 0,
  draft_revision: 1,
  metadata: { world_bundle_import: { bundle_sha256: SHA, catalog: { id: 'aurelia', author: 'someone', version: 1 } } },
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:00:00Z',
};

function renderWith(node: React.ReactNode) {
  return render(<QueryClientProvider client={createTestQueryClient()}>{node}</QueryClientProvider>);
}

describe('community worlds', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists shared worlds and sends a download to review', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push(`${init?.method ?? 'GET'} ${url}`);
      if (url.endsWith('/api/rpg/world-catalog')) {
        return jsonResponse({ ok: true, repo: 'autonomx/omnix-worlds', updated_at: '', worlds: [entry] });
      }
      if (url.endsWith('/api/rpg/world-catalog/aurelia/install')) {
        return jsonResponse({ ok: true, status: 'installed', reused: false, world_id: 'world:aurelia', version: 1, bundle_sha256: SHA, adopted: false });
      }
      return jsonResponse({ ok: true });
    }));
    const onReview = vi.fn();
    renderWith(<RpgCommunityWorlds onPlay={vi.fn()} onReview={onReview} />);

    expect(await screen.findByText('by @someone')).toBeInTheDocument();
    expect(screen.getByText('A gate opens between worlds.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));

    await waitFor(() => expect(onReview).toHaveBeenCalledWith('world:aurelia'));
    expect(calls).toContain('POST /api/rpg/world-catalog/aurelia/install');
  });

  it('plays a world already downloaded and adopted', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      ok: true,
      repo: 'autonomx/omnix-worlds',
      updated_at: '',
      worlds: [{ ...entry, installed: { world_id: 'world:aurelia', version: 1, bundle_sha256: SHA, adopted: true } }],
    })));
    const onPlay = vi.fn();
    renderWith(<RpgCommunityWorlds onPlay={onPlay} onReview={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Play' }));
    expect(onPlay).toHaveBeenCalledWith('world:aurelia');
  });

  it('adopts only after the person says they reviewed the world, naming the imported file', async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/api/rpg/worlds/world%3Aaurelia/adopt')) {
        bodies.push(JSON.parse(String(init?.body)));
        return jsonResponse({ ok: true, status: 'adopted', reused: false, world_id: 'world:aurelia', adoption: {} });
      }
      return jsonResponse({ ok: true });
    }));
    const onAdopted = vi.fn();
    renderWith(<RpgSharedWorldAdoptDialog world={sharedWorld} onAdopted={onAdopted} onCancel={vi.fn()} onEdit={vi.fn()} />);

    const adopt = screen.getByRole('button', { name: 'Adopt this world' });
    expect(adopt).toBeDisabled();
    expect(screen.getByText('@someone')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /looked through this world/ }));
    fireEvent.click(adopt);

    await waitFor(() => expect(onAdopted).toHaveBeenCalledWith('world:aurelia'));
    expect(bodies).toEqual([{ bundle_sha256: SHA }]);
  });

  it('opens the review instead of campaign setup when a shared world is played before it is adopted', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ok: true, worlds: [sharedWorld], scenarios: [], campaigns: [] })));
    renderWith(<RpgWorldAuthoringWorkspace onBack={vi.fn()} onSessionLaunched={vi.fn()} />);

    expect(await screen.findByText('Shared · review to play')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Share to community' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Review & adopt' }));
    expect(await screen.findByRole('dialog', { name: 'Review a shared world' })).toBeInTheDocument();
  });
});
