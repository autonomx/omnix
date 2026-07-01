import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ResultSummaryCard } from './ResultSummaryCard';

test('result summary renders review-required state', () => {
  render(
    <ResultSummaryCard
      payload={{
        ok: true,
        summary: 'Review the suggested next step.',
        review_required: true,
        read_only: true,
        executes: false,
      }}
    />,
  );

  expect(screen.getByLabelText('Result review summary')).toBeTruthy();
  expect(screen.getByText('Review: required')).toBeTruthy();
  expect(screen.getByText('Mode: read-only')).toBeTruthy();
  expect(screen.getByText('Execution: disabled')).toBeTruthy();
});

test('result summary exposes no action buttons', () => {
  render(<ResultSummaryCard payload={{ ok: true, summary: 'Read only.' }} />);

  expect(screen.queryByRole('button')).toBeNull();
});
