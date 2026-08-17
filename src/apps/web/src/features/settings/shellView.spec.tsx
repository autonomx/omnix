import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SettingsControlCenter } from './SettingsControlCenter';

describe('settings shell', () => {
  it('tracks provider changes, discards them, and routes categories', () => {
    render(<MantineProvider><SettingsControlCenter /></MantineProvider>);
    expect(screen.getByRole('heading', { name: 'Settings Control Center' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Fallback behavior'), { target: { value: 'fail' } });
    expect(screen.getByText('1 unsaved changes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    fireEvent.click(screen.getByRole('button', { name: /RPG/ }));
    expect(screen.getByRole('heading', { name: 'RPG' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Images & Speech Input/ }));
    expect(screen.getByRole('heading', { name: 'Images & Speech Input' })).toBeInTheDocument();
    expect(screen.getByLabelText('Width')).toBeInTheDocument();
    const categoryButtons = screen.getByLabelText('Settings categories').querySelectorAll('nav button');
    fireEvent.click(categoryButtons[9]!);
    expect(screen.getByText('Configuration ownership')).toBeInTheDocument();
    fireEvent.click(categoryButtons[10]!);
    expect(screen.getByLabelText('Retention days')).toBeInTheDocument();
    fireEvent.click(categoryButtons[11]!);
    expect(screen.getByRole('heading', { name: 'Runtime details' })).toBeInTheDocument();
  });
});
