import { describe, expect, it } from 'vitest';
import type { AssetListResponse, JobListResponse, PersistenceInventory, ReportListResponse } from '../../api/client';
import { createRpgWorkspaceState, progressPercent, safeSessionId } from './rpgUiState';

describe('rpg UI state', () => {
  it('keeps preview jobs until live RPG jobs are available', () => {
    const state = createRpgWorkspaceState({});

    expect(state.jobCards).toHaveLength(3);
    expect(state.jobCards[0]).toMatchObject({ source: 'preview', title: 'rpg.turn' });
  });

  it('normalizes live RPG sessions, jobs, assets, and reports for the workspace', () => {
    const inventory = {
      sessions: [{ session_id: 'session:live', updated_at: '2026-06-16T00:00:00Z' }],
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

    expect(state.sessions).toHaveLength(1);
    expect(state.rpgJobs).toHaveLength(1);
    expect(state.rpgAssets).toHaveLength(1);
    expect(state.rpgReports).toHaveLength(1);
    expect(state.jobCards[0]).toMatchObject({ id: 'job:rpg', progress: 25, source: 'live', title: 'rpg.turn' });
  });

  it('derives safe session labels and bounded progress percentages', () => {
    expect(safeSessionId({ name: 'named-session' }, 0)).toBe('named-session');
    expect(safeSessionId({}, 1)).toBe('session:2');
    expect(progressPercent({ current: 3, total: 4 })).toBe(75);
    expect(progressPercent({ current: 9, total: 4 })).toBe(100);
    expect(progressPercent({ current: 1, total: 0 })).toBe(0);
  });
});
