import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RpgCombatSurface } from './RpgCombatSurface';
import type { RpgFightPreview } from './rpgCombatState';

const fight: RpgFightPreview = {
  round: 3,
  yourTurn: true,
  currentName: 'Wren',
  fighters: [
    { id: 'player', name: 'Wren', side: 'party', hp: 70, maxHp: 100, percent: 70, down: false, current: true, conditions: [] },
    { id: 'enemy:wolf:1', name: 'Echo Wolf', side: 'enemy', hp: 0, maxHp: 10, percent: 0, down: true, current: false, conditions: [] },
  ],
};

describe('RpgCombatSurface', () => {
  it('shows whose turn it is and how everyone stands, in turn order', () => {
    render(<RpgCombatSurface fight={fight} />);

    expect(screen.getByRole('heading', { name: 'Your turn' })).toBeInTheDocument();
    expect(screen.getByText('Fight · round 3')).toBeInTheDocument();
    const order = screen.getByRole('list', { name: 'Turn order' });
    const [hero, wolf] = within(order).getAllByRole('listitem');
    expect(hero).toHaveAttribute('aria-current', 'step');
    expect(within(hero).getByRole('img', { name: 'Wren: 70 of 100 health' })).toBeInTheDocument();
    expect(wolf).toHaveTextContent('Out of the fight');
  });

  it('is not shown outside a fight', () => {
    const { container } = render(<RpgCombatSurface fight={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
