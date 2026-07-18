import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgLorePanel } from './RpgLorePanel';

describe('RpgLorePanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('shows the complete lore navigation and discovered dossiers', async () => {
    window.localStorage.setItem('omnix:rpg:selected-session-id', 'campaign:test');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      session_id: 'campaign:test',
      canon_revision: 2,
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
      storage: {
        mode: 'postgresql_authority',
        persisted: true,
        revision: 2,
        current_location: { id: 'location:tavern', name: 'Rusty Flagon Tavern' },
        generated_current_location: true,
      },
    }), { status: 200 })));

    render(<RpgLorePanel />);

    await waitFor(() => expect(screen.getByRole('region', { name: 'Campaign Bible summary' })).toBeInTheDocument());
    expect(screen.getByText('PostgreSQL authority')).toBeInTheDocument();
    expect(screen.getByText('Lore generated and stored')).toBeInTheDocument();

    for (const category of ['World Lore', 'Areas', 'Points of Interest', 'Characters', 'Races', 'Classes', 'Monsters', 'Items', 'Spells', 'Feats', 'Quests', 'Discoveries']) {
      expect(screen.getByRole('region', { name: category })).toBeInTheDocument();
    }

    expect(screen.getByText('Bran')).toBeInTheDocument();
    expect(screen.getAllByText('Rusty Flagon Tavern').length).toBeGreaterThan(0);
    expect(screen.getByText('Northern Watch')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Rusty Flagon Tavern/i }));
    expect(screen.getByText('Rain and hearth smoke.')).toBeInTheDocument();
  });
});
