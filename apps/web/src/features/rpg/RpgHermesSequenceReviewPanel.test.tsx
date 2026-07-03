import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
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
  it('requests a live sequence review', () => {
    const onReview = vi.fn();
    renderWithTheme(<RpgHermesSequenceReviewPanel onReview={onReview} onUseFirstItem={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Review sequence' }));

    expect(onReview).toHaveBeenCalledTimes(1);
  });

  it('changes assist mode', () => {
    const onAssistModeChange = vi.fn();
    renderWithTheme(
      <RpgHermesSequenceReviewPanel
        assistMode="review_each_step"
        onAssistModeChange={onAssistModeChange}
        onReview={vi.fn()}
        onUseFirstItem={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'auto_low_risk' }));

    expect(onAssistModeChange).toHaveBeenCalledWith('auto_low_risk');
  });

  it('fills the command box from the reviewed first item', () => {
    const onUseFirstItem = vi.fn();
    renderWithTheme(
      <RpgHermesSequenceReviewPanel
        onReview={vi.fn()}
        onUseFirstItem={onUseFirstItem}
        sequence={{
          objective: 'Review room',
          review_status: 'ready',
          validation_status: 'valid',
          gate_status: 'ready',
          first_usable_command: 'look around',
          items: [{ item_id: 'look', statement: 'look around', gate_allowed: true }],
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Use first item' }));

    expect(onUseFirstItem).toHaveBeenCalledWith('look around');
  });
});
