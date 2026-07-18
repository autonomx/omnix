import { MantineProvider } from '@mantine/core';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgHermesSequenceReviewPanel } from './RpgHermesSequenceReviewPanel';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('RpgHermesSequenceReviewPanel', () => {
  it('does not render the removed Hermes sequence review section', () => {
    const { container } = renderWithTheme(
      <RpgHermesSequenceReviewPanel onReview={vi.fn()} onUseFirstItem={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
