import { MantineProvider } from '@mantine/core';
import { render } from '@testing-library/react';
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
    const { container } = renderWithTheme(<RpgHermesExecutionHistory items={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
