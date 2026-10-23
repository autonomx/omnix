import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/renderWithProviders';
import { rpgTacticalGridClient } from './api/rpgTacticalGridClient';
import fixture from './rpgTacticalGrid.fixture.json';
import { RpgTacticalGrid } from './RpgTacticalGrid';
import type { RpgGridView } from './rpgTacticalGridModel';

const PLAYER = 'player:rpg_fixture';
const MAP = 'rpg_fixture:map:map:aurelia:arrival-grove:1';

function view(tactical: RpgGridView['tactical']): RpgGridView {
  return { ...(fixture.observe as unknown as RpgGridView), tactical };
}

afterEach(() => vi.restoreAllMocks());

describe('RpgTacticalGrid', () => {
  it('shows the local map, fog of war, who is here and the map key while exploring', async () => {
    vi.spyOn(rpgTacticalGridClient, 'observe').mockResolvedValue(view({ combat_active: false }));
    const { container } = renderWithProviders(<RpgTacticalGrid heroName="Alyndra" mapInstanceId={MAP} playerActorId={PLAYER} />);

    expect(await screen.findByRole('img', { name: 'Arrival Grove grid, 12 by 8 cells' })).toBeInTheDocument();
    expect(screen.getByText('Exploration')).toBeInTheDocument();
    expect(container.querySelectorAll('.rpg-grid-terrain-unknown').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('.rpg-grid-reachable')).toHaveLength(0);
    const roster = screen.getByRole('region', { name: 'Who is here' });
    expect(within(roster).getByText('Alyndra (you)')).toBeInTheDocument();
    expect(within(roster).getByText('Liora Fen')).toBeInTheDocument();

    fireEvent.click(container.querySelector('[data-cell="5,6"]')!);
    const selected = screen.getByRole('region', { name: 'Selected cell' });
    expect(within(selected).getByText('To Starfall Village')).toBeInTheDocument();
    expect(within(selected).queryByRole('button', { name: 'Move here' })).toBeNull();
  });

  it('lights reachable cells on your turn and moves with the revisions the server checks', async () => {
    vi.spyOn(rpgTacticalGridClient, 'observe').mockResolvedValue(view({
      combat_active: true, round: 1, current_actor_id: PLAYER, your_turn: true, movement_remaining: 20, actions_remaining: 1,
      hostile_actor_ids: ['npc:liora-fen'],
    }));
    const move = vi.spyOn(rpgTacticalGridClient, 'move').mockResolvedValue({ ok: true });
    const attack = vi.spyOn(rpgTacticalGridClient, 'attack').mockResolvedValue({ ok: true });
    const { container } = renderWithProviders(<RpgTacticalGrid heroName="Alyndra" mapInstanceId={MAP} playerActorId={PLAYER} />);

    expect(await screen.findByText('Your turn · 20 movement · 1 action')).toBeInTheDocument();
    expect(container.querySelectorAll('.rpg-grid-reachable').length).toBeGreaterThan(0);
    fireEvent.click(container.querySelector('[data-cell="4,3"]')!);
    fireEvent.click(screen.getByRole('button', { name: 'Move here' }));
    await waitFor(() => expect(move).toHaveBeenCalledWith(MAP, {
      actorId: PLAYER, destination: [4, 3], campaignRevision: 3, mapStateRevision: fixture.observe.projection.map_state_revision }));

    fireEvent.click(screen.getByRole('button', { name: 'Attack Liora Fen' }));
    await waitFor(() => expect(attack).toHaveBeenCalledWith(MAP, expect.objectContaining({ targetId: 'npc:liora-fen' })));
  });

  it('waits on another actor’s turn without offering moves', async () => {
    vi.spyOn(rpgTacticalGridClient, 'observe').mockResolvedValue(view({
      combat_active: true, round: 2, current_actor_id: 'npc:liora-fen', your_turn: false, movement_remaining: 60, actions_remaining: 1,
    }));
    const { container } = renderWithProviders(<RpgTacticalGrid heroName="Alyndra" mapInstanceId={MAP} playerActorId={PLAYER} />);

    expect(await screen.findByText("Liora Fen's turn")).toBeInTheDocument();
    expect(container.querySelectorAll('.rpg-grid-reachable')).toHaveLength(0);
  });
});
