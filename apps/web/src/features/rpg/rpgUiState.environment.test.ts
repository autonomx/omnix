import { describe, expect, it } from 'vitest';
import { createRpgWorkspaceState } from './rpgUiState';

describe('RPG environment UI state', () => {
  it('loads preview rows', () => {
    const state = createRpgWorkspaceState({});
    expect(state.worldStateRows.length).toBeGreaterThan(0);
  });
});
