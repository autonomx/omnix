import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgHermesSequenceJobPanel } from './RpgHermesSequenceJobPanel';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('RpgHermesSequenceJobPanel', () => {
  it('renders progress and controls', () => {
    const onCancel = vi.fn();
    renderWithTheme(
      <RpgHermesSequenceJobPanel
        activeJob={{ id: 'job-1', status: 'running', stages: [{ status: 'completed' }, { status: 'queued' }] } as never}
        onCancel={onCancel}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStart={vi.fn()}
      />,
    );

    expect(screen.getByRole('region', { name: 'Hermes sequence job' })).toHaveTextContent('50%');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
