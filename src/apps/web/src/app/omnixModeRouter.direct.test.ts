import { describe, expect, it } from 'vitest';
import { getOmnixModeRoute, usesExistingOmnixPath } from './omnixModeRouter';

describe('existing Omnix paths', () => {
  it('keeps normal and live on existing paths', () => {
    expect(getOmnixModeRoute('normal')).toMatchObject({ path: 'direct', needsReview: false });
    expect(getOmnixModeRoute('live')).toMatchObject({ path: 'live', needsReview: false });
    expect(usesExistingOmnixPath('normal')).toBe(true);
    expect(usesExistingOmnixPath('live')).toBe(true);
  });

  it('does not mark new lanes as existing paths', () => {
    expect(usesExistingOmnixPath('agent')).toBe(false);
    expect(usesExistingOmnixPath('house')).toBe(false);
    expect(usesExistingOmnixPath('podcast')).toBe(false);
    expect(usesExistingOmnixPath('rpg')).toBe(false);
  });
});
