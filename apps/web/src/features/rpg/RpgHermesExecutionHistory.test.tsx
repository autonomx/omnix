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
  it('does not render the removed Hermes history section', () => {
    renderWithTheme(<RpgHermesExecutionHistory items={[]} />);

    expect(screen.queryByText('Hermes history')).not.toBeInTheDocument();
    expect(screen.queryByText('No Hermes execution history for this session yet.')).not.toBeInTheDocument();
  });
});
