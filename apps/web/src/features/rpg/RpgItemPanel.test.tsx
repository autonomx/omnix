import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RpgItemPanel } from './RpgItemPanel';
import type { RpgItemObjectivePreview, RpgItemUiAction, RpgMerchantEntryPreview } from './rpgItemUiState';

const action: RpgItemUiAction = {
  id: 'use:field-kit',
  kind: 'use',
  label: 'Use',
  detail: 'Apply item effects.',
  mode: 'loadout',
  command: 'Use Field Kit',
  payload: { action: 'use', item_name: 'Field Kit' },
  item: { label: 'Field Kit', icon: '🧰', count: 1, sessionId: null },
};

const objective: RpgItemObjectivePreview = {
  id: 'craft:torch',
  label: 'Craft torch',
  detail: 'Enough materials are available.',
  action: 'craft',
  payload: { recipe_id: 'torch' },
};

const merchantEntry: RpgMerchantEntryPreview = {
  id: 'buy:torch',
  label: 'Torch',
  detail: 'Useful light source.',
  priceLabel: '1s',
  action: 'buy',
  payload: { action: 'buy', item_name: 'Torch' },
};

function renderItemPanel(element: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{element}</QueryClientProvider>);
}

describe('RpgItemPanel', () => {
  it('renders an empty state when no selected item actions are available', () => {
    renderItemPanel(<RpgItemPanel actions={[]} />);

    expect(screen.getByText('Inventory, crafting, and trade')).toBeInTheDocument();
    expect(screen.getByText('No item selected')).toBeInTheDocument();
    expect(screen.getByText('Select an inventory item to reveal deterministic actions.')).toBeInTheDocument();
  });

  it('renders preview details for the selected item', () => {
    renderItemPanel(<RpgItemPanel actions={[action]} />);

    const detailCard = screen.getByLabelText('Selected item details: Field Kit');
    expect(detailCard).toHaveTextContent('Preview item details');
    expect(detailCard).toHaveTextContent('Field Kit');
    expect(detailCard).toHaveTextContent('1 carried');
  });

  it('applies selected item actions through callbacks', () => {
    const onApplyAction = vi.fn();
    renderItemPanel(<RpgItemPanel actions={[action]} onApplyAction={onApplyAction} />);

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onApplyAction).toHaveBeenCalledWith(action);
  });

  it('falls back to command selection when no action callback is present', () => {
    const onSelectCommand = vi.fn();
    renderItemPanel(<RpgItemPanel actions={[action]} onSelectCommand={onSelectCommand} />);

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onSelectCommand).toHaveBeenCalledWith('Use Field Kit');
  });

  it('renders status cards, objectives, and merchant entries', () => {
    const onApplyObjective = vi.fn();
    const onApplyMerchantEntry = vi.fn();
    renderItemPanel(
      <RpgItemPanel
        actions={[action]}
        merchantEntries={[merchantEntry]}
        objectives={[objective]}
        onApplyMerchantEntry={onApplyMerchantEntry}
        onApplyObjective={onApplyObjective}
        statusCards={[{ id: 'coverage', label: 'Item coverage', value: '75%', detail: '3 of 4 pillars covered.', tone: 'warning' }]}
      />,
    );

    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('Suggested next item steps')).toBeInTheDocument();
    expect(screen.getByText('Merchant service')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Craft torch' }));
    fireEvent.click(screen.getByRole('button', { name: 'buy Torch' }));

    expect(onApplyObjective).toHaveBeenCalledWith(objective);
    expect(onApplyMerchantEntry).toHaveBeenCalledWith(merchantEntry);
  });

  it('disables actionable rows while pending', () => {
    renderItemPanel(<RpgItemPanel actions={[action]} isPending />);

    expect(screen.getByRole('button', { name: 'Use' })).toBeDisabled();
  });
});
