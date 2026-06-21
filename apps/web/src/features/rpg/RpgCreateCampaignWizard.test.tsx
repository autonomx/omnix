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

function getSelectByVisibleLabel(label: string): HTMLSelectElement {
  const labelNode = screen.getByText(label).closest('label');
  const select = labelNode?.querySelector('select');
  if (!select) {
    throw new Error(`Could not find select for ${label}`);
  }
  return select;
}

function backendStages(status: 'completed' | 'failed' = 'completed') {
  const labels = [
    'Backend validated setup',
    'Backend resolved seed',
    'Backend created player',
    'Backend applied stats',
    'Backend assigned gear',
    'Backend location',
    'Backend seeded NPCs',
    'Backend opening hook',
    'Backend saved session',
    'Backend first turn',
  ];
  return labels.map((label, index) => ({
    detail: index === 9 ? 'Backend context ready' : `Backend stage ${index}`,
    index,
    label,
    progress: [8, 18, 31, 44, 56, 68, 78, 88, 96, 100][index],
    status: status === 'completed' ? 'done' : index < 5 ? 'done' : index === 5 ? 'failed' : 'pending',
  }));
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

  it('uses pending and backend progress and fills an enter-world command after API completion', async () => {
    vi.useFakeTimers();
    const onSelectCommand = vi.fn();
    let resolveLaunch!: (value: {
      creation_progress: Record<string, unknown>;
      ok: true;
      session_id: string;
    }) => void;
    const onCreateCampaign = vi.fn(
      () =>
        new Promise<{ creation_progress: Record<string, unknown>; ok: true; session_id: string }>((resolve) => {
          resolveLaunch = resolve;
        }),
    );
    renderWithTheme(<RpgCreateCampaignWizard onCreateCampaign={onCreateCampaign} onSelectCommand={onSelectCommand} />);

    fireEvent.change(getSelectByVisibleLabel('Opening hook'), { target: { value: 'merchant-job' } });
    fireEvent.change(getSelectByVisibleLabel('Relationship preset'), { target: { value: 'known-contact' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));

    expect(screen.getByRole('dialog', { name: 'Creating Campaign' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByRole('button', { name: 'Enter World' })).toBeDisabled();
    expect(onCreateCampaign).toHaveBeenCalledWith(
      expect.objectContaining({
        companions_enabled: true,
        initial_stats: expect.objectContaining({ strength: 9, perception: 9 }),
        opening_hook: 'merchant_job',
        opening_pace: 'balanced',
        player: expect.objectContaining({ build: 'balanced_adventurer', name: 'Elara', pronouns: 'she/her' }),
        primary_capability: 'recon',
        relationship_preset: 'known_contact_nearby',
        seed: 482193,
        starter_gear_tags: expect.arrayContaining(['Travel cloak', 'Iron dagger']),
        starting_location: 'rusty_flagon_tavern',
        story_options: expect.objectContaining({ opening_hook_label: 'Merchant Job', relationship_label: 'Known contact nearby' }),
      }),
    );

    act(() => {
      vi.advanceTimersByTime(1200);
    });

    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '31');
    expect(screen.getByText(/Created player profile:/)).toBeInTheDocument();

    await act(async () => {
      resolveLaunch({
        ok: true,
        session_id: 'session-new',
        creation_progress: {
          current_stage_index: 9,
          progress: 100,
          stage: 'prepare_first_turn',
          stage_label: 'Backend first turn',
          stages: backendStages('completed'),
          status: 'completed',
        },
      });
      await Promise.resolve();
    });

    expect(screen.getByRole('dialog', { name: 'Campaign Ready' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByText('Backend first turn: Backend context ready')).toBeInTheDocument();
    expect(screen.getByText('Session session-new')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enter World' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Enter World' }));

    expect(onSelectCommand).toHaveBeenCalledWith(expect.stringContaining('Session session-new is ready'));
    expect(onSelectCommand).toHaveBeenCalledWith(expect.stringContaining('Opening: Merchant Job'));
    vi.useRealTimers();
  });

  it('keeps the modal open and reports backend creation progress errors', async () => {
    const onCreateCampaign = vi.fn(async () => ({
      ok: false,
      error: 'invalid point-buy payload',
      creation_progress: {
        current_stage_index: 5,
        error: 'invalid point-buy payload',
        progress: 68,
        stage: 'prepare_location',
        stage_label: 'Backend location',
        stages: backendStages('failed'),
        status: 'failed',
      },
    }));
    renderWithTheme(<RpgCreateCampaignWizard onCreateCampaign={onCreateCampaign} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));
      await Promise.resolve();
    });

    expect(screen.getByRole('dialog', { name: 'Campaign Creation Failed' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Campaign creation progress' })).toHaveAttribute('aria-valuenow', '68');
    expect(screen.getByText(/Failed at Backend location: invalid point-buy payload/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enter World' })).toBeDisabled();
  });
});