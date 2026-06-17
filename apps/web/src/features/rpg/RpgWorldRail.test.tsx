import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgWorldRail } from './RpgWorldRail';
import {
  npcRelationships,
  previewEncounter,
  previewJobs,
  previewSessionSummary,
  previewWorldStateRows,
} from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgWorldRail', () => {
  it('renders world state, encounter, relationships, jobs, and reports', () => {
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
    expect(screen.getByRole('button', { name: 'Change location' })).toBeInTheDocument();
    expect(screen.getByText('World state')).toBeInTheDocument();
    expect(screen.getByText('Day 18 • 09:42')).toBeInTheDocument();
    expect(screen.getByLabelText('No active combat encounter state')).toBeInTheDocument();
    expect(screen.getByText('Preview encounter state')).toBeInTheDocument();
    expect(screen.getByText('Thorin Ironfist')).toBeInTheDocument();
    expect(screen.getByText('RPG jobs')).toBeInTheDocument();
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(screen.getByLabelText('rpg.turn progress')).toBeInTheDocument();
    expect(screen.getByText('2 ready')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open reports index' })).toHaveAttribute('href', '/api/reports');
    expect(screen.getByText('Latest checkpoint: checkpoint-001.json')).toBeInTheDocument();
    expect(screen.getByText('rpg_checkpoint / rpg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create checkpoint' })).toBeInTheDocument();
  });

  it('wires live control callbacks', () => {
    const onCreateCheckpoint = vi.fn();
    const onRefreshJobs = vi.fn();
    const onToggleAutoplay = vi.fn();

    renderWithTheme(
      <RpgWorldRail
        autoplayRunning={false}
        autoplayStatusLabel="Off"
        checkpointControlStatus="Ready to save"
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
    expect(screen.getByText('Ready to save')).toBeInTheDocument();
  });

  it('renders pending and running live-control states', () => {
    renderWithTheme(
      <RpgWorldRail
        autoplayRunning
        autoplayStatusLabel="running • job-1"
        checkpointControlStatus="Creating checkpoint…"
        checkpointSummary={{ label: 'Latest checkpoint', detail: 'checkpoint-001.json', source: 'live' }}
        encounter={previewEncounter}
        isAutoplayPending={false}
        isCreatingCheckpoint
        isRefreshingJobs
        jobCards={previewJobs}
        npcRelationships={npcRelationships}
        onCreateCheckpoint={vi.fn()}
        onRefreshJobs={vi.fn()}
        onToggleAutoplay={vi.fn()}
        reportsHref="/api/reports"
        rpgAssets={[]}
        rpgJobCount={1}
        rpgReportCount={0}
        selectedSessionSummary={previewSessionSummary}
        worldStateRows={previewWorldStateRows}
      />
    );

    expect(screen.getByRole('button', { name: 'Refreshing…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Stop autoplay' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Creating checkpoint…' })).toBeDisabled();
    expect(screen.getByText('running • job-1')).toBeInTheDocument();
  });
});
