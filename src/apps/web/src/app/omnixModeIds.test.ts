import { describe, expect, it } from 'vitest';
import { getOmnixModeInfo, isOmnixModeId, OMNIX_MODE_IDS } from './omnixModeIds';

describe('omnix mode ids', () => {
  it('lists the supported UI modes in router order', () => {
    expect(OMNIX_MODE_IDS).toEqual(['normal', 'live', 'agent', 'house', 'podcast', 'rpg']);
  });

  it('validates mode ids', () => {
    expect(isOmnixModeId('rpg')).toBe(true);
    expect(isOmnixModeId('unknown')).toBe(false);
  });

  it('returns mode display info', () => {
    expect(getOmnixModeInfo('podcast').label).toBe('Podcast');
  });
});
