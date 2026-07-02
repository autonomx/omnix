import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { HermesSequenceBox } from './HermesSequenceBox';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('HermesSequenceBox', () => {
  it('renders empty and ready status states', () => {
    renderWithTheme(<HermesSequenceBox response={null} />);
    expect(screen.getByRole('region', { name: 'Hermes sequence box' })).toHaveTextContent('not checked');
  });

  it('renders mapped sequence content', () => {
    renderWithTheme(
      <HermesSequenceBox
        response={{
          ok: true,
          sequence: {
            sequence_id: 'seq-1',
            objective: 'Room details',
            domain: 'rpg',
            state_owner: 'rpg_sim',
            items: [{ item_id: 'item-1', statement: 'inspect room', user_gate: false }],
          },
        }}
      />,
    );

    expect(screen.getByRole('region', { name: 'Hermes sequence box' })).toHaveTextContent('ready');
    expect(screen.getByText('Room details')).toBeInTheDocument();
    expect(screen.getByText('inspect room')).toBeInTheDocument();
  });
});
