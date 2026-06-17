import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { hotbarAbilities, inventoryItems } from './rpgUiState';

describe('RpgLoadoutTabs', () => {
  it('renders inventory by default and switches to abilities and hotbar panels', () => {
    render(<RpgLoadoutTabs hotbarAbilities={hotbarAbilities} inventoryItems={inventoryItems} />);

    expect(screen.getByRole('tab', { name: 'Inventory' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Inventory' })).toHaveTextContent('12');
    expect(screen.getByRole('button', { name: 'Healing potion' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Abilities' }));

    expect(screen.getByRole('tab', { name: 'Abilities' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Abilities' })).toHaveTextContent('Aimed Shot');

    fireEvent.click(screen.getByRole('tab', { name: 'Hotbar' }));

    expect(screen.getByRole('tab', { name: 'Hotbar' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Hotbar' })).toHaveTextContent('Keyboard-ready hotbar');
    expect(screen.getByRole('button', { name: '1: Aimed Shot' })).toBeInTheDocument();
  });
});
