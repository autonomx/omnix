import { describe, expect, it } from 'vitest';
import { buildItemDetailPreview, buildSelectedItemActions } from './rpgItemUiState';

const cloak = {
  icon: '◇', count: '1', label: 'Travel Cloak', actions: ['unequip', 'drop', 'sell'], category: 'clothing',
  description: 'keeps the rain off', worn: true,
};

describe('rpg item UI state', () => {
  it('offers the actions the game says the item has, each a turn', () => {
    const actions = buildSelectedItemActions({ item: cloak, selectedSessionId: 'session-live' });

    expect(actions.map((action) => action.label)).toEqual(['Unequip', 'Drop', 'Sell']);
    expect(actions[0]).toMatchObject({ mode: 'loadout', payload: { action: 'unequip', item_name: 'Travel Cloak' }, disabled: false });
    expect(actions[2]).toMatchObject({ mode: 'turn', command: 'I sell the Travel Cloak.' });
  });

  it('ignores actions it does not know, and offers nothing without a campaign', () => {
    const actions = buildSelectedItemActions({ item: { ...cloak, actions: ['salvage', 'use'] }, selectedSessionId: null });

    expect(actions.map((action) => action.kind)).toEqual(['use']);
    expect(actions.every((action) => action.disabled)).toBe(true);
  });

  it('describes the item from the world, with whether it is worn', () => {
    expect(buildItemDetailPreview(cloak)).toEqual({
      itemName: 'Travel Cloak', icon: '◇', countLabel: '1 carried', summary: 'Keeps the rain off.', status: 'Worn',
      category: 'clothing',
    });
    expect(buildItemDetailPreview({ icon: '◇', count: '2', label: 'Rope' })?.summary).toBe('Nothing more is known of it.');
  });
});
