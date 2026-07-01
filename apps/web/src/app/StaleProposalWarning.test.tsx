import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { StaleProposalWarning } from './StaleProposalWarning';

test('stale proposal warning renders when stale', () => {
  render(<StaleProposalWarning stale />);

  expect(screen.getByLabelText('Stale proposal warning')).toBeTruthy();
  expect(screen.getByText('Stale proposal')).toBeTruthy();
  expect(screen.getByText(/Request a fresh review before use./)).toBeTruthy();
  expect(screen.queryByRole('button')).toBeNull();
});

test('stale proposal warning hides when current', () => {
  render(<StaleProposalWarning stale={false} />);

  expect(screen.queryByLabelText('Stale proposal warning')).toBeNull();
});
