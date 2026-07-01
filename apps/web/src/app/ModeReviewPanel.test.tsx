import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ModeReviewPanel } from './ModeReviewPanel';

test('renders mode review panel', () => {
  render(<ModeReviewPanel mode="normal" input="x" />);

  expect(screen.getByText('Normal chat')).toBeTruthy();
  expect(screen.getByText('Path: direct')).toBeTruthy();
  expect(screen.getByText('Review: not required')).toBeTruthy();
});
