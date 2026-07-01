import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { SidecarStatusCard } from './SidecarStatusCard';

test('sidecar status card renders disabled state safely', () => {
  render(<SidecarStatusCard payload={{ enabled: false }} />);

  expect(screen.getByLabelText('Sidecar status')).toBeTruthy();
  expect(screen.getByText('Status: disabled')).toBeTruthy();
  expect(screen.getByText('Service is disabled.')).toBeTruthy();
  expect(screen.getByText('Execution: disabled')).toBeTruthy();
});

test('sidecar status card renders healthy and error states safely', () => {
  const { rerender } = render(<SidecarStatusCard payload={{ ok: true, status: 'healthy' }} />);
  expect(screen.getByText('Status: ready')).toBeTruthy();
  expect(screen.getByText('healthy')).toBeTruthy();

  rerender(<SidecarStatusCard error="Unavailable" />);
  expect(screen.getByText('Status: error')).toBeTruthy();
  expect(screen.getByText('Unavailable')).toBeTruthy();
  expect(screen.queryByRole('button')).toBeNull();
});
