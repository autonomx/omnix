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
  it('renders deep setup controls, point buy, story hooks, starter gear, and supported systems', () => {
    renderWithTheme(<RpgCreateCampaignWizard />);

    expect(screen.getByRole('heading', { name: 'Create Campaign' })).toBeInTheDocument();
    expect(screen.getByLabelText('Secondary capabilities')).toHaveTextContent('Combat');
    expect(screen.getByLabelText('Campaign setup summary')).toHaveTextContent('Rusty Flagon Tavern');
    expect(screen.getByLabelText('Campaign setup summary')).toHaveTextContent('Tavern Rumor');
    expect(screen.getByLabelText('Campaign setup summary')).toHaveTextContent('Unknown outsider');
    expect(screen.getByText('Opening story')).toBeInTheDocument();
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

  it('posts a normalized new-game request and fills an enter-world command after API completion', async () => {
    vi.useFakeTimers();
    const onSelectCommand = vi.fn();
    let resolveLaunch!: (value: { ok: true; session_id: string }) => void;
    const onCreateCampaign = vi.fn(
      () =>
        new Promise<{ ok: true; session_id: string }>((resolve) => {
          resolveLaunch = resolve;
        }),
    );
    renderWithTheme(<RpgCreateCampaignWizard onCreateCampaign={onCreateCampaign} onSelectCommand={onSelectCommand} />);

    fireEvent.change(screen.getByLabelText('Opening hook'), { target: { value: 'merchant-job' } });
    fireEvent.change(screen.getByLabelText('Relationship preset'), { target: { value: 'known-contact' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));

    expect(screen.getByRole('dialog', { name: 'Creating Campaign' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByRole('button', { name: 'Enter World' })).toBeDisabled();
    expect(onCreateCampaign).toHaveBeenCalledWith(
      expect.objectContaining({
        companions_enabled: true,
        initial_stats: expect.objectContaining({ strength: 8, perception: 8 }),
        opening_hook: 'merchant_job',
        opening_pace: 'balanced',
        player: expect.objectContaining({ build: 'balanced_adventurer', name: 'Elara', pronouns: 'she/her' }),
        primary_capability: 'recon',
        relationship_preset: 'known_contact_nearby',
        starting_location: 'rusty_flagon_tavern',
        story_options: expect.objectContaining({ opening_hook_label: 'Merchant Job', relationship_label: 'Known contact nearby' }),
      }),
    );

    act(() => {
      vi.advanceTimersByTime(1200);
    });

    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).not.toHaveAttribute('aria-valuenow', '100');

    await act(async () => {
      resolveLaunch({ ok: true, session_id: 'session-new' });
      await Promise.resolve();
    });

    expect(screen.getByRole('dialog', { name: 'Campaign Ready' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByText('Session session-new')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enter World' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Enter World' }));

    expect(onSelectCommand).toHaveBeenCalledWith(expect.stringContaining('Session session-new is ready'));
    expect(onSelectCommand).toHaveBeenCalledWith(expect.stringContaining('Opening: Merchant Job'));
    vi.useRealTimers();
  });

  it('keeps the modal open and reports errors when campaign creation fails', async () => {
    const onCreateCampaign = vi.fn(async () => ({ ok: false, error: 'invalid point-buy payload' }));
    renderWithTheme(<RpgCreateCampaignWizard onCreateCampaign={onCreateCampaign} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));
      await Promise.resolve();
    });

    expect(screen.getByRole('dialog', { name: 'Campaign Creation Failed' })).toBeInTheDocument();
    expect(screen.getByText(/invalid point-buy payload/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enter World' })).toBeDisabled();
  });
});
