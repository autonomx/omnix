import { describe, expect, it } from 'vitest';
import type { AssetListResponse, JobListResponse, PersistenceInventory, ReportListResponse } from '../../api/client';
import { createRpgWorkspaceState, progressPercent, safeSessionId } from './rpgUiState';

describe('rpg UI state', () => {
  it('keeps preview jobs until live RPG jobs are available', () => {
    const state = createRpgWorkspaceState({});

    expect(state.jobCards).toHaveLength(3);
    expect(state.jobCards[0]).toMatchObject({ source: 'preview', title: 'rpg.turn' });
    expect(state.selectedSessionSummary).toMatchObject({ source: 'preview', title: 'Preview campaign' });
    expect(state.journalDetail.title).toBe('Arrived at Glimmerdeep Pass');
  });

  it('normalizes live RPG sessions, jobs, assets, and reports for the workspace', () => {
    const inventory = {
      sessions: [
        {
          session_id: 'session:older',
          updated_at: '2026-06-15T00:00:00Z',
          title: 'Older session',
          location: 'Old Road',
          turn_count: 3,
        },
        {
          session_id: 'session:live',
          updated_at: '2026-06-16T00:00:00Z',
          title: 'Live campaign',
          location: 'Rusty Flagon Tavern',
          summary: 'Bran is waiting near the bar with news about the quarry.',
          turn_count: 12,
          checkpoint_path: 'checkpoints/live.json',
        },
      ],
      diagnostics: [],
    } as PersistenceInventory;
    const jobs = {
      jobs: [
        {
          id: 'job:rpg',
          module: 'rpg',
          type: 'rpg.turn',
          status: 'running',
          resource_class: 'gpu:llm',
          priority: 0,
          progress: { current: 1, total: 4 },
          stages: [{ id: 'narrate', label: 'Generate narration', resource_class: 'gpu:llm', status: 'running' }],
          created_at: '2026-06-16T00:00:00Z',
          updated_at: '2026-06-16T00:00:00Z',
        },
        {
          id: 'job:chat',
          module: 'chat',
          type: 'chat.generate',
          status: 'queued',
          resource_class: 'gpu:llm',
          priority: 0,
          created_at: '2026-06-16T00:00:00Z',
          updated_at: '2026-06-16T00:00:00Z',
        },
      ],
    } as JobListResponse;
    const assets = {
      assets: [
        {
          id: 'asset:rpg',
          module: 'rpg',
          type: 'rpg_checkpoint',
          mime_type: 'application/json',
          storage_path: 'checkpoints/session.json',
          created_at: '2026-06-16T00:00:00Z',
        },
        {
          id: 'asset:chat',
          module: 'chat',
          type: 'chat_transcript',
          mime_type: 'application/json',
          storage_path: 'chat/session.json',
          created_at: '2026-06-16T00:00:00Z',
        },
      ],
    } as AssetListResponse;
    const reports = {
      reports: [
        { id: 'rpg/autoplay.json', kind: 'rpg_autoplay', path: 'reports/rpg/autoplay.json', size_bytes: 42 },
        { id: 'chat/summary.json', kind: 'chat_summary', path: 'reports/chat/summary.json', size_bytes: 42 },
      ],
    } as ReportListResponse;

    const state = createRpgWorkspaceState({ inventory, jobs, assets, reports });

    expect(state.sessions).toHaveLength(2);
    expect(state.sessionSummaries[0]).toMatchObject({
      id: 'session:live',
      title: 'Live campaign',
      location: 'Rusty Flagon Tavern',
      turnLabel: 'Turn 12',
      updatedAt: '2026-06-16 00:00 UTC',
    });
    expect(state.selectedSessionSummary.id).toBe('session:live');
    expect(state.recentEvents[0]).toBe('Loaded Live campaign.');
    expect(state.journalDetail).toMatchObject({
      title: 'Live session: Live campaign',
      tags: ['Live session', 'Replay-safe', 'Indexed'],
    });
    expect(state.worldStateRows[0]).toMatchObject({ label: 'Updated', value: '2026-06-16 00:00 UTC' });
    expect(state.checkpointSummary).toMatchObject({ label: 'Latest checkpoint', detail: 'checkpoints/session.json' });
    expect(state.rpgJobs).toHaveLength(1);
    expect(state.rpgAssets).toHaveLength(1);
    expect(state.rpgReports).toHaveLength(1);
    expect(state.jobCards[0]).toMatchObject({ id: 'job:rpg', progress: 25, source: 'live', title: 'rpg.turn' });
  });

  it('keeps a user-selected RPG session active when multiple sessions exist', () => {
    const inventory = {
      sessions: [
        { session_id: 'newer', title: 'Newer', updated_at: '2026-06-16T00:00:00Z' },
        { session_id: 'chosen', title: 'Chosen', location: 'Market Ward', updated_at: '2026-06-14T00:00:00Z', current_turn: '8' },
      ],
      diagnostics: [],
    } as PersistenceInventory;

    const state = createRpgWorkspaceState({ inventory, selectedSessionId: 'chosen' });

    expect(state.selectedSessionSummary).toMatchObject({
      id: 'chosen',
      title: 'Chosen',
      location: 'Market Ward',
      turnLabel: 'Turn 8',
    });
    expect(state.journalEntries[0]).toMatchObject({ title: 'Selected Chosen' });
  });

  it('derives safe session labels and bounded progress percentages', () => {
    expect(safeSessionId({ name: 'named-session' }, 0)).toBe('named-session');
    expect(safeSessionId({}, 1)).toBe('session:2');
    expect(progressPercent({ current: 3, total: 4 })).toBe(75);
    expect(progressPercent({ current: 9, total: 4 })).toBe(100);
    expect(progressPercent({ current: 1, total: 0 })).toBe(0);
  });
});
