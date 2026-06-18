import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { hotbarAbilities, inventoryItems } from './rpgUiState';

type LoadoutTabsProps = Parameters<typeof RpgLoadoutTabs>[0];

function renderLoadoutTabs(props: LoadoutTabsProps) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <RpgLoadoutTabs {...props} />
    </QueryClientProvider>,
  );
}

describe('RpgLoadoutTabs', () => {
  it('renders inventory by default and switches to abilities and hotbar panels', () => {
    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand: vi.fn() });

    expect(screen.getByRole('tab', { name: 'Inventory' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Inventory' })).toHaveTextContent('12');
    expect(screen.getByRole('button', { name: 'Healing potion' })).toBeInTheDocument();
    expect(screen.getByLabelText('Selected item: Healing potion')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Abilities' }));

    expect(screen.getByRole('tab', { name: 'Abilities' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Abilities' })).toHaveTextContent('Aimed Shot');
    expect(screen.getByRole('complementary', { name: 'Active ability: Aimed Shot' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Hotbar' }));

    expect(screen.getByRole('tab', { name: 'Hotbar' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Hotbar' })).toHaveTextContent('Frost Arrow');
    expect(screen.getByRole('button', { name: /Aimed Shot/ })).toBeInTheDocument();
  });

  it('turns inventory and ability interactions into replay-preserving commands', () => {
    const onSelectCommand = vi.fn();
    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand });

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onSelectCommand).toHaveBeenCalledWith('Use Healing potion if it is helpful and legal in the current situation.');

    fireEvent.click(screen.getByRole('button', { name: 'Trail rations' }));
    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }));

    expect(onSelectCommand).toHaveBeenLastCalledWith('Inspect Trail rations and describe its useful properties.');

    fireEvent.click(screen.getByRole('tab', { name: 'Abilities' }));
    const activeAbility = screen.getByRole('complementary', { name: 'Active ability: Aimed Shot' });
    fireEvent.click(within(activeAbility).getByRole('button', { name: 'Use' }));

    expect(onSelectCommand).toHaveBeenLastCalledWith('Use Aimed Shot on the most relevant target.');

    fireEvent.click(screen.getByRole('tab', { name: 'Hotbar' }));
    fireEvent.click(screen.getByRole('button', { name: /Frost Arrow/ }));

    expect(onSelectCommand).toHaveBeenLastCalledWith('Use Frost Arrow from hotbar slot 2 on the best available target.');
  });
});
