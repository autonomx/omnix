import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

describe('RpgItemPanel', () => {
  it('renders an empty state when no selected item actions are available', () => {
    render(<RpgItemPanel actions={[]} />);

    expect(screen.getByText('Inventory, crafting, and trade')).toBeInTheDocument();
    expect(screen.getByText('No item selected')).toBeInTheDocument();
    expect(screen.getByText('Select an inventory item to reveal deterministic actions.')).toBeInTheDocument();
  });

  it('applies selected item actions through callbacks', async () => {
    const onApplyAction = vi.fn();
    render(<RpgItemPanel actions={[action]} onApplyAction={onApplyAction} />);

    await userEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onApplyAction).toHaveBeenCalledWith(action);
  });

  it('falls back to command selection when no action callback is present', async () => {
    const onSelectCommand = vi.fn();
    render(<RpgItemPanel actions={[action]} onSelectCommand={onSelectCommand} />);

    await userEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onSelectCommand).toHaveBeenCalledWith('Use Field Kit');
  });

  it('renders status cards, objectives, and merchant entries', async () => {
    const onApplyObjective = vi.fn();
    const onApplyMerchantEntry = vi.fn();
    render(
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

    await userEvent.click(screen.getByRole('button', { name: 'Craft torch' }));
    await userEvent.click(screen.getByRole('button', { name: 'buy Torch' }));

    expect(onApplyObjective).toHaveBeenCalledWith(objective);
    expect(onApplyMerchantEntry).toHaveBeenCalledWith(merchantEntry);
  });

  it('disables actionable rows while pending', () => {
    render(<RpgItemPanel actions={[action]} isPending />);

    expect(screen.getByRole('button', { name: 'Use' })).toBeDisabled();
  });
});
