import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgHermesExecutionResult } from './RpgHermesExecutionResult';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('RpgHermesExecutionResult', () => {
  it('renders nothing without a result', () => {
    renderWithTheme(<RpgHermesExecutionResult result={null} />);

    expect(screen.queryByRole('region', { name: 'Hermes execution result' })).not.toBeInTheDocument();
  });

  it('renders approved execution details', () => {
    renderWithTheme(
      <RpgHermesExecutionResult
        result={{
          ok: true,
          state_changed: true,
          readout: { command_text: 'look around', systems: ['journal'] },
          flow: { result: { rpg_result: { turn: 9, narration: 'You look around.' } } },
          ledger_entry: { execution_id: 'hermes-rpg-1' },
        }}
      />,
    );

    expect(screen.getByRole('region', { name: 'Hermes execution result' })).toHaveTextContent('look around');
    expect(screen.getByText('You look around.')).toBeInTheDocument();
    expect(screen.getByText('hermes-rpg-1')).toBeInTheDocument();
  });
});
