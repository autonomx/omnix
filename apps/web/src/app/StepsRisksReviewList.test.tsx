import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { StepsRisksReviewList } from './StepsRisksReviewList';

test('steps risks review list renders read-only proposal details', () => {
  render(
    <StepsRisksReviewList
      steps={[{ id: 's1', title: 'Read', description: 'Inspect.', status: 'ready' }]}
      risks={[{ id: 'r1', label: 'Boundary', message: 'Do not apply.', severity: 'high' }]}
    />,
  );

  expect(screen.getByLabelText('Proposal steps and risks')).toBeTruthy();
  expect(screen.getByText(/Review required before any use./)).toBeTruthy();
  expect(screen.getByText('Read')).toBeTruthy();
  expect(screen.getByText('Boundary')).toBeTruthy();
  expect(screen.queryByRole('button')).toBeNull();
});
