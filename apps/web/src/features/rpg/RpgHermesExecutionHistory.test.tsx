import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgHermesExecutionHistory } from './RpgHermesExecutionHistory';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('RpgHermesExecutionHistory', () => {
  it('renders empty history', () => {
    renderWithTheme(<RpgHermesExecutionHistory items={[]} />);

    expect(screen.getByText('No Hermes execution history for this session yet.')).toBeInTheDocument();
  });

  it('renders ledger items', () => {
    renderWithTheme(
      <RpgHermesExecutionHistory
        items={[{ execution_id: 'e1', command_text: 'look around', sequence_id: 'seq-1', state_changed: true, result_summary: 'You look around.' }]}
      />,
    );

    expect(screen.getByRole('region', { name: 'Hermes execution history' })).toHaveTextContent('look around');
    expect(screen.getByText('You look around.')).toBeInTheDocument();
  });
});
