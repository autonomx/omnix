import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgWorldRail } from './RpgWorldRail';
import { npcRelationships, previewEncounter, previewJobs, previewSessionSummary, previewWorldStateRows } from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgWorldRail', () => {
  it('renders snapshot world rows without unwired map buttons', () => {
    renderWithTheme(
      <RpgWorldRail
        autoplayRunning={false}
        autoplayStatusLabel="Off"
        checkpointSummary={{ label: 'Latest checkpoint', detail: 'checkpoint-001.json', source: 'live' }}
        encounter={previewEncounter}
        isAutoplayPending={false}
        isCreatingCheckpoint={false}
        isRefreshingJobs={false}
        jobCards={previewJobs}
        npcRelationships={npcRelationships}
        onCreateCheckpoint={vi.fn()}
        onRefreshJobs={vi.fn()}
        onToggleAutoplay={vi.fn()}
        reportsHref="/api/reports"
        rpgAssets={[{ id: 'asset-1', module: 'rpg', storage_path: 'sessions/checkpoint-001.json', type: 'rpg_checkpoint' }]}
        rpgJobCount={0}
        rpgReportCount={2}
        selectedSessionSummary={previewSessionSummary}
        worldStateRows={previewWorldStateRows}
      />
    );

    expect(screen.getByRole('complementary', { name: 'World, jobs, and reports' })).toBeInTheDocument();
    expect(screen.getByLabelText('Glimmerdeep Pass travel map')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Change location' })).not.toBeInTheDocument();
    expect(screen.getByText('Calendar / Season')).toBeInTheDocument();
    expect(screen.getByText('Hazards')).toBeInTheDocument();
    expect(screen.getByText('NPC relationships')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open reports index' })).toHaveAttribute('href', '/api/reports');
    expect(screen.getByText('Latest checkpoint: checkpoint-001.json')).toBeInTheDocument();
    expect(screen.getByText('rpg_checkpoint / rpg')).toBeInTheDocument();
  });

  it('keeps the wired job, autoplay, and checkpoint controls active', () => {
    const onCreateCheckpoint = vi.fn();
    const onRefreshJobs = vi.fn();
    const onToggleAutoplay = vi.fn();

    renderWithTheme(
      <RpgWorldRail
        autoplayRunning={false}
        autoplayStatusLabel="Off"
        checkpointSummary={{ label: 'Latest checkpoint', detail: 'checkpoint-001.json', source: 'live' }}
        encounter={previewEncounter}
        isAutoplayPending={false}
        isCreatingCheckpoint={false}
        isRefreshingJobs={false}
        jobCards={previewJobs}
        npcRelationships={npcRelationships}
        onCreateCheckpoint={onCreateCheckpoint}
        onRefreshJobs={onRefreshJobs}
        onToggleAutoplay={onToggleAutoplay}
        reportsHref="/api/reports"
        rpgAssets={[]}
        rpgJobCount={1}
        rpgReportCount={1}
        selectedSessionSummary={previewSessionSummary}
        worldStateRows={previewWorldStateRows}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Refresh RPG jobs' }));
    fireEvent.click(screen.getByRole('button', { name: 'Start autoplay' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create checkpoint' }));

    expect(onRefreshJobs).toHaveBeenCalledTimes(1);
    expect(onToggleAutoplay).toHaveBeenCalledTimes(1);
    expect(onCreateCheckpoint).toHaveBeenCalledTimes(1);
  });

  it('caps the RPG jobs rail to three visible jobs', () => {
    renderWithTheme(
      <RpgWorldRail
        autoplayRunning={false}
        autoplayStatusLabel="Off"
        checkpointSummary={{ label: 'Latest checkpoint', detail: 'checkpoint-001.json', source: 'live' }}
        encounter={previewEncounter}
        isAutoplayPending={false}
        isCreatingCheckpoint={false}
        isRefreshingJobs={false}
        jobCards={[
          { id: 'job-1', title: 'rpg.turn', status: 'completed', progress: 100, detail: 'First job', source: 'live' },
          { id: 'job-2', title: 'rpg.turn', status: 'completed', progress: 100, detail: 'Second job', source: 'live' },
          { id: 'job-3', title: 'rpg.turn', status: 'completed', progress: 100, detail: 'Third job', source: 'live' },
          { id: 'job-4', title: 'rpg.turn', status: 'completed', progress: 100, detail: 'Fourth job', source: 'live' },
        ]}
        npcRelationships={npcRelationships}
        onCreateCheckpoint={vi.fn()}
        onRefreshJobs={vi.fn()}
        onToggleAutoplay={vi.fn()}
        reportsHref="/api/reports"
        rpgAssets={[]}
        rpgJobCount={4}
        rpgReportCount={1}
        selectedSessionSummary={{ ...previewSessionSummary, id: 'live-session', source: 'live' }}
        worldStateRows={previewWorldStateRows}
      />
    );

    expect(screen.getByText('3 live')).toBeInTheDocument();
    expect(screen.getByText('First job')).toBeInTheDocument();
    expect(screen.getByText('Second job')).toBeInTheDocument();
    expect(screen.getByText('Third job')).toBeInTheDocument();
    expect(screen.queryByText('Fourth job')).not.toBeInTheDocument();
  });
});
