import { describe, expect, it } from 'vitest';
import { hermesSequencePreviewModel } from './hermesSequencePreviewModel';

describe('preview model mapper', () => {
  it('maps populated input', () => {
    const result = hermesSequencePreviewModel({
      ok: true,
      sequence: {
        sequence_id: 'seq-1',
        objective: 'Room details',
        domain: 'rpg',
        state_owner: 'rpg_sim',
        risk: 'low',
        items: [{ item_id: 'item-1', statement: 'inspect room', user_gate: false }],
      },
    });

    expect(result?.sequence_id).toBe('seq-1');
    expect(result?.items?.[0]?.statement).toBe('inspect room');
    expect(result?.items?.[0]?.user_gate).toBe(false);
  });

  it('returns null for empty input', () => {
    expect(hermesSequencePreviewModel(null)).toBeNull();
    expect(hermesSequencePreviewModel({ ok: false })).toBeNull();
  });
});
