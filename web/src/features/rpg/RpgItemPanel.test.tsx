import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RpgItemPanel } from './RpgItemPanel';
import type { RpgItemUiAction } from './rpgItemUiState';

const action: RpgItemUiAction = {
  id: 'use:field-kit',
  kind: 'use',
  label: 'Use',
  detail: 'Use the Field Kit.',
  mode: 'loadout',
  command: 'Use Field Kit',
  payload: { action: 'use', item_name: 'Field Kit' },
};

const fieldKit = { label: 'Field Kit', icon: '🧰', count: '1', category: 'tool', description: 'mends torn straps' };

describe('RpgItemPanel', () => {
  it('asks the player to select something when nothing is', () => {
    render(<RpgItemPanel actions={[]} />);

    expect(screen.getByText('Select something you carry.')).toBeInTheDocument();
  });

  it('shows what the world says of the selected item, with no model call', () => {
    render(<RpgItemPanel actions={[action]} item={fieldKit} />);

    const detailCard = screen.getByLabelText('Selected item details: Field Kit');
    expect(detailCard).toHaveTextContent('tool');
    expect(detailCard).toHaveTextContent('Mends torn straps.');
    expect(detailCard).toHaveTextContent('1 carried');
    expect(detailCard).toHaveTextContent('StatusCarried');
  });

  it('applies selected item actions through its callback', () => {
    const onApplyAction = vi.fn();
    render(<RpgItemPanel actions={[action]} item={fieldKit} onApplyAction={onApplyAction} />);

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onApplyAction).toHaveBeenCalledWith(action);
  });

  it('holds actions while one is on its way, and without a campaign', () => {
    const { unmount } = render(<RpgItemPanel actions={[action]} item={fieldKit} isPending />);
    expect(screen.getByRole('button', { name: 'Use' })).toBeDisabled();
    unmount();
    render(<RpgItemPanel actions={[{ ...action, disabled: true }]} item={fieldKit} />);
    expect(screen.getByRole('button', { name: 'Use' })).toHaveAttribute('title', 'Use: Start or load a campaign first.');
  });
});
