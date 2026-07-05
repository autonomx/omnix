import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SettingsControlCenter } from './SettingsControlCenter';

describe('settings shell', () => {
  it('renders and changes category', () => {
    render(<SettingsControlCenter />);
    expect(screen.getByRole('heading', { name: 'Settings Control Center' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'AI Providers' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /RPG/ }));
    expect(screen.getByRole('heading', { name: 'RPG' })).toBeInTheDocument();
  });
});
