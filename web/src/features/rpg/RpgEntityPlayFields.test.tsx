import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RpgEntityPlayFields } from './RpgEntityPlayFields';

describe('RpgEntityPlayFields', () => {
  it("writes an item's gear: the slot it is worn in and its numbers", () => {
    const onChange = vi.fn();
    const { rerender } = render(<RpgEntityPlayFields entity={{ id: 'item:blade', kind: 'item' }} title="Blade" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Worn as'), { target: { value: 'main_hand' } });
    expect(onChange).toHaveBeenLastCalledWith({ id: 'item:blade', kind: 'item', equipment: { slot: 'main_hand' } });
    rerender(<RpgEntityPlayFields entity={{ id: 'item:blade', kind: 'item', equipment: { slot: 'main_hand' } }} title="Blade" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Damage to'), { target: { value: '6' } });
    expect(onChange).toHaveBeenLastCalledWith({ id: 'item:blade', kind: 'item', equipment: { slot: 'main_hand', stats: { damage_max: 6 } } });
  });

  it("writes a character's home, aliases and group", () => {
    const onChange = vi.fn();
    render(<RpgEntityPlayFields entity={{ id: 'npc:orik', kind: 'npc' }} title="Orik" onChange={onChange} />);
    const aliases = screen.getByLabelText('Aliases (comma separated)');
    fireEvent.change(aliases, { target: { value: 'the innkeeper, Old ' } });
    expect(aliases).toHaveValue('the innkeeper, Old ');  // typed as it is, spaces and commas kept
    fireEvent.change(aliases, { target: { value: 'the innkeeper, Old Orik' } });
    fireEvent.blur(aliases);
    expect(onChange).toHaveBeenLastCalledWith({ id: 'npc:orik', kind: 'npc', aliases: ['the innkeeper', 'Old Orik'] });
    fireEvent.change(screen.getByLabelText('Group (a group id)'), { target: { value: 'faction:wardens' } });
    expect(onChange).toHaveBeenLastCalledWith({ id: 'npc:orik', kind: 'npc', group_id: 'faction:wardens' });
  });
});
