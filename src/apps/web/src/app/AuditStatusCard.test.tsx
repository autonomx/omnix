import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { AuditStatusCard } from './AuditStatusCard';

test('audit status card renders compact read-only audit status', () => {
  render(
    <AuditStatusCard
      payload={{
        source: 'plan_request',
        timestamp: '2026-01-01T00:00:00Z',
        review_required: true,
        read_only: true,
        executes: false,
      }}
    />,
  );

  expect(screen.getByLabelText('Audit status')).toBeTruthy();
  expect(screen.getByText('Source: plan_request')).toBeTruthy();
  expect(screen.getByText('Review: required')).toBeTruthy();
  expect(screen.getByText('Mode: read-only')).toBeTruthy();
  expect(screen.getByText('Execution: disabled')).toBeTruthy();
  expect(screen.queryByRole('button')).toBeNull();
});
