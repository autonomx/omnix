import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixApiClient } from '../../api/client';
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
    expect(screen.getByText('Last 10 turn debug report')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate last 10 turn report' })).toBeDisabled();
  });

  it('keeps the wired job, autoplay, report, and checkpoint controls active', async () => {
    const onCreateCheckpoint = vi.fn();
    const onRefreshJobs = vi.fn();
    const onToggleAutoplay = vi.fn();
    const createJobSpy = vi.spyOn(omnixApiClient, 'createJob').mockResolvedValue({
      id: 'job:report-1',
      module: 'rpg',
      type: 'rpg.report.last10',
      status: 'queued',
      resource_class: 'cpu',
      priority: 0,
      stages: [],
      progress: { current: 0, total: 1 },
      logs: [],
      input_ref: { session_id: 'session-live-1' },
      input_payload: {},
      output_refs: [],
      created_at: '2026-06-23T00:00:00Z',
      updated_at: '2026-06-23T00:00:00Z',
      cancel: { requested: false },
      compat: {},
    });

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
        selectedSessionSummary={{ ...previewSessionSummary, id: 'session-live-1', source: 'live' }}
        worldStateRows={previewWorldStateRows}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Refresh RPG jobs' }));
    fireEvent.click(screen.getByRole('button', { name: 'Start autoplay' }));
    fireEvent.click(screen.getByRole('button', { name: 'Generate last 10 turn report' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create checkpoint' }));

    expect(onToggleAutoplay).toHaveBeenCalledTimes(1);
    expect(onCreateCheckpoint).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(createJobSpy).toHaveBeenCalledTimes(1));
    expect(createJobSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        module: 'rpg',
        type: 'rpg.report.last10',
        resource_class: 'cpu',
        input_ref: { session_id: 'session-live-1' },
        input_payload: expect.objectContaining({ turn_limit: 10, include_performance_metrics: true }),
      }),
      expect.objectContaining({ timeoutMs: 45_000 }),
    );
    await waitFor(() => expect(onRefreshJobs).toHaveBeenCalledTimes(2));
    await screen.findByText('queued • job:report-1');
    createJobSpy.mockRestore();
  });

  it('shows at most three RPG job cards while preserving the live count', () => {
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
          { id: 'job-1', title: 'rpg.turn.1', status: 'Completed', progress: 100, detail: 'First job', source: 'live' },
          { id: 'job-2', title: 'rpg.turn.2', status: 'Completed', progress: 100, detail: 'Second job', source: 'live' },
          { id: 'job-3', title: 'rpg.turn.3', status: 'Running', progress: 50, detail: 'Third job', source: 'live' },
          { id: 'job-4', title: 'rpg.turn.4', status: 'Queued', progress: 0, detail: 'Fourth job', source: 'live' },
        ]}
        npcRelationships={npcRelationships}
        onCreateCheckpoint={vi.fn()}
        onRefreshJobs={vi.fn()}
        onToggleAutoplay={vi.fn()}
        reportsHref="/api/reports"
        rpgAssets={[]}
        rpgJobCount={4}
        rpgReportCount={0}
        selectedSessionSummary={previewSessionSummary}
        worldStateRows={previewWorldStateRows}
      />
    );

    expect(screen.getByText('4 live')).toBeInTheDocument();
    expect(screen.getByText('rpg.turn.1')).toBeInTheDocument();
    expect(screen.getByText('rpg.turn.2')).toBeInTheDocument();
    expect(screen.getByText('rpg.turn.3')).toBeInTheDocument();
    expect(screen.queryByText('rpg.turn.4')).not.toBeInTheDocument();
  });

  it('shows the failure reason for failed RPG job cards', () => {
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
          {
            id: 'job-report-failed',
            title: 'rpg.report.last10',
            status: 'failed',
            progress: 66,
            detail: 'Load RPG session / Collect last 10 turns / Write debug ZIP report',
            errorDetail: 'Last 10 turn report failed before ZIP creation.',
            source: 'live',
          },
        ]}
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

    expect(screen.getByText('rpg.report.last10')).toBeInTheDocument();
    expect(screen.getByText('Reason: Last 10 turn report failed before ZIP creation.')).toBeInTheDocument();
  });
});
