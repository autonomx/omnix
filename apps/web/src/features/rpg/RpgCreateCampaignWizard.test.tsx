import { MantineProvider } from '@mantine/core';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgCreateCampaignWizard } from './RpgCreateCampaignWizard';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>,
  );
}

describe('RpgCreateCampaignWizard', () => {
  it('renders deep setup controls, point buy, starter gear, and supported systems', () => {
    renderWithTheme(<RpgCreateCampaignWizard />);

    expect(screen.getByRole('heading', { name: 'Create Campaign' })).toBeInTheDocument();
    expect(screen.getByLabelText('Secondary capabilities')).toHaveTextContent('Combat');
    expect(screen.getByLabelText('Campaign setup summary')).toHaveTextContent('Rusty Flagon Tavern');
    expect(screen.getByText('Starter gear')).toBeInTheDocument();
    expect(screen.getByText('Grounding validator')).toBeInTheDocument();
    expect(screen.getByText('20 points left')).toBeInTheDocument();
  });

  it('spends stat points and prevents overspending', () => {
    renderWithTheme(<RpgCreateCampaignWizard />);

    fireEvent.click(screen.getByRole('button', { name: 'Increase Strength' }));
    fireEvent.click(screen.getByRole('button', { name: 'Increase Charisma' }));

    expect(screen.getByText('18 points left')).toBeInTheDocument();
    expect(screen.getByLabelText('Derived stat preview')).toHaveTextContent('Strength: 10');
  });

  it('shows a staged creation progress modal and fills an enter-world command when complete', () => {
    vi.useFakeTimers();
    const onSelectCommand = vi.fn();
    renderWithTheme(<RpgCreateCampaignWizard onSelectCommand={onSelectCommand} />);

    fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));

    expect(screen.getByRole('dialog', { name: 'Creating Campaign' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByRole('button', { name: 'Enter World' })).toBeDisabled();

    act(() => {
      vi.advanceTimersByTime(4200);
    });

    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByRole('button', { name: 'Enter World' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Enter World' }));

    expect(onSelectCommand).toHaveBeenCalledWith(expect.stringContaining('Begin a new Balanced Adventurer campaign for Elara'));
    vi.useRealTimers();
  });
});
