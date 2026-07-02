import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { HermesSequencePreview } from './HermesSequencePreview';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('HermesSequencePreview', () => {
  it('renders an empty preview state', () => {
    renderWithTheme(<HermesSequencePreview sequence={null} />);

    expect(screen.getByText('No Hermes sequence is ready for review.')).toBeInTheDocument();
  });

  it('renders sequence metadata and items', () => {
    renderWithTheme(
      <HermesSequencePreview
        sequence={{
          sequence_id: 'seq-1',
          objective: 'Review the current location',
          domain: 'rpg',
          state_owner: 'rpg_sim',
          risk: 'low',
          status: 'ready',
          items: [
            { item_id: 'look', statement: 'look around', expected_effect: 'Current room details refresh.' },
            { item_id: 'local', statement: 'ask for a local update', expected_effect: 'Local context is updated.', user_gate: true },
          ],
        }}
      />,
    );

    expect(screen.getByRole('region', { name: 'Hermes sequence preview' })).toHaveTextContent('Review the current location');
    expect(screen.getByText('low')).toBeInTheDocument();
    expect(screen.getByText('rpg_sim')).toBeInTheDocument();
    expect(screen.getByText('look around')).toBeInTheDocument();
    expect(screen.getByText('Local context is updated.')).toBeInTheDocument();
  });
});
