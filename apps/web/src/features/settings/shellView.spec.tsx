import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SettingsControlCenter } from './SettingsControlCenter';

describe('settings shell', () => {
  it('tracks provider changes, discards them, and changes category', () => {
    render(<MantineProvider><SettingsControlCenter /></MantineProvider>);
    expect(screen.getByRole('heading', { name: 'Settings Control Center' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'AI Providers' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Fallback behavior'), { target: { value: 'fail' } });
    expect(screen.getByText('1 unsaved changes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getByText('Saved')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /RPG/ }));
    expect(screen.getByRole('heading', { name: 'RPG' })).toBeInTheDocument();
  });
});
