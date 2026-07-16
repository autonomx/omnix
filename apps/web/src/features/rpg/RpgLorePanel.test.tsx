import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgLorePanel } from './RpgLorePanel';

describe('RpgLorePanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('renders player-safe character, location, and faction dossiers', async () => {
    window.localStorage.setItem('omnix:rpg:selected-session-id', 'campaign:test');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      session_id: 'campaign:test',
      canon_revision: 1,
      content_hash: 'sha256:test',
      categories: [],
      visible_count: 0,
      hidden_count: 2,
      dossiers: {
        characters: [{ id: 'npc:bran', kind: 'npc', name: 'Bran', status: 'partially_known', appearance: 'A watchful innkeeper.' }],
        locations: [{ id: 'location:tavern', kind: 'location', name: 'Rusty Flagon Tavern', status: 'partially_known', sensory_profile: 'Rain and hearth smoke.' }],
        factions: [{ id: 'faction:watch', kind: 'faction', name: 'Northern Watch', status: 'partially_known', public_goal: 'Keep the roads safe.' }],
      },
      generation: { status: 'ready', launch_ready: true, percent: 100, jobs: [] },
    }), { status: 200 })));

    render(<RpgLorePanel />);

    await waitFor(() => expect(screen.getByText('Known world dossiers')).toBeInTheDocument());
    expect(screen.getByText('Bran')).toBeInTheDocument();
    expect(screen.getByText('Rusty Flagon Tavern')).toBeInTheDocument();
    expect(screen.getByText('Northern Watch')).toBeInTheDocument();
    expect(screen.getByText('A watchful innkeeper.')).toBeInTheDocument();
  });
});
