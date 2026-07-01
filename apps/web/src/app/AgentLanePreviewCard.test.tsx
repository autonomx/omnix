import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { AgentLanePreviewCard } from './AgentLanePreviewCard';

test('renders agent lane review status', () => {
  render(<AgentLanePreviewCard input="x" />);

  expect(screen.getByText('Agent mode')).toBeTruthy();
  expect(screen.getByText('Path: adapter')).toBeTruthy();
  expect(screen.getByText('Review: required')).toBeTruthy();
});
