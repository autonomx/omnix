import { describe, expect, it } from 'vitest';
import { getOmnixModeRoute } from './omnixModeRouter';

describe('getOmnixModeRoute', () => {
  it('routes each shared mode to a stable path', () => {
    expect(getOmnixModeRoute('normal').path).toBe('direct');
    expect(getOmnixModeRoute('live').path).toBe('live');
    expect(getOmnixModeRoute('agent').path).toBe('adapter');
    expect(getOmnixModeRoute('house').path).toBe('review');
    expect(getOmnixModeRoute('podcast').path).toBe('audio');
    expect(getOmnixModeRoute('rpg').path).toBe('sim');
  });

  it('marks review-gated lanes', () => {
    expect(getOmnixModeRoute('normal').needsReview).toBe(false);
    expect(getOmnixModeRoute('agent').needsReview).toBe(true);
    expect(getOmnixModeRoute('podcast').needsReview).toBe(true);
  });
});
