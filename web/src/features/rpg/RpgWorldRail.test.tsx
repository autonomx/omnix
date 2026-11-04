import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RpgWorldRail } from './RpgWorldRail';
import { previewHere, previewJobs, previewSessionSummary, previewWorldStateRows } from './rpgUiPreview';
import { renderWithProviders } from '../../test/renderWithProviders';


const baseProps = {
  autoplayRunning: false,
  autoplayStatusLabel: 'Autoplay off',
  checkpointSummary: { label: 'Latest checkpoint', detail: 'checkpoint-001.json', source: 'live' as const },
  developerTools: true, // the jobs card is a developer panel
  isAutoplayPending: false,
  isRefreshingJobs: false,
  here: previewHere,
  jobCards: previewJobs,
  onRefreshJobs: vi.fn(),
  onSelectCommand: vi.fn(),
  onToggleAutoplay: vi.fn(),
  rpgAssets: [{ id: 'asset-1', module: 'rpg', file_name: 'checkpoint-001.json', type: 'rpg_checkpoint' }],
  rpgJobCount: 0,
  selectedSessionSummary: previewSessionSummary,
  worldStateRows: previewWorldStateRows,
};

describe('RpgWorldRail', () => {
  it('keeps world information without restoring the Autoplay & reports section', () => {
    renderWithProviders(<RpgWorldRail {...baseProps} />);

    expect(screen.getByRole('complementary', { name: 'World and places' })).toBeInTheDocument();
    expect(screen.getByLabelText('Glimmerdeep Pass travel map')).toBeInTheDocument();
    expect(screen.getByText('Hazards')).toBeInTheDocument();
    expect(screen.queryByText('Calendar / Season')).not.toBeInTheDocument(); // in the World panel
    expect(screen.queryByText('People you know')).not.toBeInTheDocument(); // in the World panel
    expect(screen.getByText('RPG jobs')).toBeInTheDocument();

    expect(screen.queryByText('Autoplay & reports')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Generate last 10 turn report' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open reports index' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start autoplay' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create checkpoint' })).not.toBeInTheDocument(); // save points replace it
    expect(screen.getByRole('heading', { name: 'rpg_checkpoint / rpg' })).toBeInTheDocument();
  });

  it('keeps job and compact runtime controls active', () => {
    const onRefreshJobs = vi.fn();
    const onToggleAutoplay = vi.fn();
    renderWithProviders(
      <RpgWorldRail
        {...baseProps}
        onRefreshJobs={onRefreshJobs}
        onToggleAutoplay={onToggleAutoplay}
        rpgJobCount={1}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Refresh RPG jobs' }));
    fireEvent.click(screen.getByRole('button', { name: 'Start autoplay' }));
    expect(onRefreshJobs).toHaveBeenCalledTimes(1);
    expect(onToggleAutoplay).toHaveBeenCalledTimes(1);
    expect(screen.getByText('1 live')).toBeInTheDocument();
  });

  it('shows at most three RPG job cards and preserves failure details', () => {
    renderWithProviders(
      <RpgWorldRail
        {...baseProps}
        jobCards={[
          { id: 'job-1', title: 'rpg.turn.1', status: 'Completed', progress: 100, detail: 'First job', source: 'live' },
          { id: 'job-2', title: 'rpg.turn.2', status: 'Completed', progress: 100, detail: 'Second job', source: 'live' },
          {
            id: 'job-3',
            title: 'rpg.report.last10',
            status: 'failed',
            progress: 66,
            detail: 'Report job retained in job history',
            errorDetail: 'Last 10 turn report failed before ZIP creation.',
            source: 'live',
          },
          { id: 'job-4', title: 'rpg.turn.4', status: 'Queued', progress: 0, detail: 'Fourth job', source: 'live' },
        ]}
        rpgJobCount={4}
      />,
    );

    expect(screen.getByText('4 live')).toBeInTheDocument();
    expect(screen.getByText('rpg.turn.1')).toBeInTheDocument();
    expect(screen.getByText('rpg.turn.2')).toBeInTheDocument();
    expect(screen.getByText('rpg.report.last10')).toBeInTheDocument();
    expect(screen.getByText('Reason: Last 10 turn report failed before ZIP creation.')).toBeInTheDocument();
    expect(screen.queryByText('rpg.turn.4')).not.toBeInTheDocument();
  });

  it('keeps the jobs card for developers', () => {
    renderWithProviders(<RpgWorldRail {...baseProps} developerTools={false} />);
    expect(screen.queryByText('RPG jobs')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start autoplay' })).not.toBeInTheDocument();
  });

  it('prepares a turn from who is here and where the paths lead', () => {
    const onSelectCommand = vi.fn();
    renderWithProviders(<RpgWorldRail {...baseProps} developerTools={false} onSelectCommand={onSelectCommand} />);

    fireEvent.click(within(screen.getByRole('group', { name: 'People here' })).getByRole('button', { name: 'Thorin Ironfist' }));
    expect(onSelectCommand).toHaveBeenLastCalledWith('I talk to Thorin Ironfist.');
    fireEvent.click(within(screen.getByRole('group', { name: 'Paths from here' })).getByRole('button', { name: 'Frostbound Hollow' }));
    expect(onSelectCommand).toHaveBeenLastCalledWith('go to Frostbound Hollow');
  });

  it('says so when no one else is here and offers no paths it does not know', () => {
    renderWithProviders(<RpgWorldRail {...baseProps} developerTools={false} here={{ people: [], exits: [] }} />);
    expect(screen.getByText('No one else is here.')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Paths from here' })).not.toBeInTheDocument();
  });
});
