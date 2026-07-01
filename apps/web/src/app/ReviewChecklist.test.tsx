import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ReviewChecklist } from './ReviewChecklist';

test('review checklist renders read-only checklist items', () => {
  render(<ReviewChecklist mode="rpg" />);

  expect(screen.getByLabelText('Review checklist')).toBeTruthy();
  expect(screen.getByText(/User reviewed proposal/)).toBeTruthy();
  expect(screen.getByText(/No execution performed/)).toBeTruthy();
  expect(screen.getByText(/Simulation validation required for RPG/)).toBeTruthy();
  expect(screen.queryByRole('button')).toBeNull();
});
