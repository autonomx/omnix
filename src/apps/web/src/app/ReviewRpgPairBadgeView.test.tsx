import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ReviewRpgPairBadgeView } from './ReviewRpgPairBadgeView';
import { createReviewRpgPairStatus } from './reviewRpgPairStatus';

test('review rpg pair badge view renders passive status text', () => {
  render(<ReviewRpgPairBadgeView status={createReviewRpgPairStatus()} />);

  const badge = screen.getByLabelText(/Status:/);
  expect(badge.textContent).toContain('Awaiting review context');
  expect(badge.getAttribute('data-read-only')).toBe('true');
  expect(badge.getAttribute('data-passive')).toBe('true');
});
