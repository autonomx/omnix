import { describe, expect, it, vi } from 'vitest';
import { fetchRpgAbilityDetails, type RpgItemApiClient } from './rpgItemApi';

function fakeClient() {
  const post = vi.fn(async (_path: `/api/${string}`, body: Record<string, unknown>) => ({ ok: true, body }));
  return { client: { post } as RpgItemApiClient, post };
}

describe('rpg ability detail API', () => {
  it('posts ability detail requests for a hotbar tooltip', async () => {
    const { client, post } = fakeClient();

    await fetchRpgAbilityDetails('session-1', { abilityName: 'Frost Arrow', abilityId: 'recon_frost_arrow' }, client);

    expect(post).toHaveBeenCalledWith('/api/rpg/session/get', {
      action: 'ability_detail',
      session_id: 'session-1',
      ability_name: 'Frost Arrow',
      ability_id: 'recon_frost_arrow',
      source: 'rpg-hotbar-tooltip',
    });
  });
});
