import { beforeEach, describe, expect, it, vi } from 'vitest';
import { omnixApiClient } from './client';
import { checkHermesRpgSequence } from './hermesRpgSequenceClient';

vi.mock('./client', () => ({
  omnixApiClient: {
    post: vi.fn(),
  },
}));

describe('hermesRpgSequenceClient', () => {
  beforeEach(() => {
    vi.mocked(omnixApiClient.post).mockReset();
  });

  it('posts sequence data to the sequence endpoint', async () => {
    vi.mocked(omnixApiClient.post).mockResolvedValue({ ok: true });

    const request = {
      sequence_id: 'seq-1',
      objective: 'Review room details',
      domain: 'rpg',
      state_owner: 'rpg_sim',
      items: [{ item_id: 'look', statement: 'look around' }],
    };
    const result = await checkHermesRpgSequence(request);

    expect(result).toEqual({ ok: true });
    expect(omnixApiClient.post).toHaveBeenCalledWith('/api/hermes/rpg/sequence/review', request);
  });
});
