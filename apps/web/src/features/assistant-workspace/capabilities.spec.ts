import { describe, expect, it } from 'vitest';
import { getEnabledCapabilities } from './capabilities';

describe('capability contracts', () => {
  it('filters enabled records', () => {
    const enabled = { id: 'c1', name: 'Search', description: 'Find things', scope: 'workspace' as const, enabled: true };
    const disabled = { ...enabled, id: 'c2', enabled: false };
    expect(getEnabledCapabilities([enabled, disabled])).toEqual([enabled]);
  });
});
