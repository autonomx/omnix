import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { RpgPlayPanels, type RpgPlayPanelId } from './RpgPlayPanels';

function Harness({ initial = null }: { initial?: RpgPlayPanelId | null }) {
  const [open, setOpen] = useState<RpgPlayPanelId | null>(initial);
  return (
    <>
      <textarea aria-label="Command" />
      <RpgPlayPanels open={open} onChange={setOpen}>{open ? <p>Inside {open}</p> : null}</RpgPlayPanels>
    </>
  );
}

const bar = (name: string) => screen.getByRole('button', { name });

describe('RpgPlayPanels', () => {
  it('opens one panel at a time from the bar, and closes it from the bar or its own button', () => {
    render(<Harness />);
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(bar('Inventory')).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(bar('Inventory'));
    expect(screen.getByRole('region', { name: 'Inventory' })).toHaveTextContent('Inside pack');
    expect(bar('Inventory')).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(bar('Journal'));
    expect(screen.queryByRole('region', { name: 'Inventory' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Journal' })).toBeInTheDocument();

    fireEvent.click(bar('Journal'));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();

    fireEvent.click(bar('World'));
    fireEvent.click(screen.getByRole('button', { name: 'Close panel' }));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('moves focus into the panel and gives it back when Escape closes it', () => {
    render(<Harness />);
    bar('Character').focus();
    fireEvent.click(bar('Character'));
    expect(screen.getByRole('heading', { name: 'Character' })).toHaveFocus();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(bar('Character')).toHaveFocus();
  });

  it('opens and closes panels by their keys', () => {
    render(<Harness />);
    for (const [key, name] of [['i', 'Inventory'], ['c', 'Character'], ['j', 'Journal'], ['l', 'World']]) {
      fireEvent.keyDown(document.body, { key });
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
    fireEvent.keyDown(document.body, { key: 'l' });
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('leaves the keys alone while the player is typing or another dialog is open', () => {
    render(<Harness />);
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Command' }), { key: 'i' });
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: 'i', ctrlKey: true });
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('leaves the keys to a dialog open over the screen', () => {
    render(<><Harness /><div aria-modal="true" role="dialog" aria-label="Map" /></>);
    fireEvent.keyDown(document.body, { key: 'i' });
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('shows the panels the bar has no button for, under their own names', () => {
    render(<Harness initial="game-master" />);
    expect(screen.getByRole('region', { name: 'Game master' })).toHaveTextContent('Inside game-master');
  });
});
