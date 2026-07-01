import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ModeReviewCard } from './ModeReviewCard';

test('renders mode review status', () => {
  render(<ModeReviewCard mode="agent" input="x" />);

  expect(screen.getByText('Agent mode')).toBeTruthy();
  expect(screen.getByText('Path: adapter')).toBeTruthy();
  expect(screen.getByText('Review: required')).toBeTruthy();
});
