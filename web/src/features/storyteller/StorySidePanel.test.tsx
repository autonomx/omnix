import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { type StorySideTab, StorySidePanel } from './StorySidePanel';

function Panel() {
  const [active, setActive] = useState<StorySideTab>('write');
  return (
    <StorySidePanel
      active={active}
      onChange={setActive}
      panels={{ write: <p>Outline here</p>, characters: <p>Cast here</p>, world: <p>Notes here</p>, audio: <p>Voices here</p> }}
    />
  );
}

afterEach(() => window.localStorage.clear());

describe('StorySidePanel', () => {
  it('folds into a rail of its tabs, opens again on the tab chosen there, and remembers being folded', () => {
    const { unmount } = render(<Panel />);
    expect(screen.getByText('Outline here')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Hide the story panel' }));
    expect(screen.getByText('Outline here')).not.toBeVisible();
    expect(screen.getByRole('button', { name: 'Show the story panel' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('tab', { name: 'Audio' })).toBeInTheDocument();

    unmount();
    render(<Panel />);
    expect(screen.getByText('Outline here')).not.toBeVisible();

    fireEvent.click(screen.getByRole('tab', { name: 'Audio' }));
    expect(screen.getByText('Voices here')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Hide the story panel' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens from the rail on an arrow key too, and names the panels its fold button shows and hides', () => {
    render(<Panel />);
    const foldButton = screen.getByRole('button', { name: 'Hide the story panel' });
    const panelIds = screen.getAllByRole('tabpanel', { hidden: true }).map((panel) => panel.id);
    expect(foldButton.getAttribute('aria-controls')?.split(' ')).toEqual(panelIds);
    expect(screen.getByRole('region', { name: 'Story side panel' })).toBeInTheDocument();

    fireEvent.click(foldButton);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Write' }), { key: 'ArrowDown' });
    expect(screen.getByRole('tab', { name: 'Characters' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Characters' })).toHaveFocus();
    expect(screen.getByText('Cast here')).toBeVisible();
  });
});
