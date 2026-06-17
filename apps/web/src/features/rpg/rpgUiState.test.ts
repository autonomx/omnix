import { describe, expect, it } from 'vitest';
import type { AssetListResponse, JobListResponse, PersistenceInventory, ReportListResponse } from '../../api/client';
import { createRpgWorkspaceState, progressPercent, safeSessionId } from './rpgUiState';

describe('rpg UI state', () => {
  it('keeps preview jobs until live RPG jobs are available', () => {
    const state = createRpgWorkspaceState({});

    expect(state.jobCards).toHaveLength(3);
    expect(state.jobCards[0]).toMatchObject({ source: 'preview', title: 'rpg.turn' });
    expect(state.selectedSessionSummary).toMatchObject({ source: 'preview', title: 'Preview campaign' });
    expect(state.heroSummary).toMatchObject({ source: 'preview', name: 'Alyndra' });
    expect(state.journalDetail.title).toBe('Arrived at Glimmerdeep Pass');
    expect(state.encounter).toMatchObject({ source: 'preview', title: 'No active combat' });
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
    expect(state.worldStateRows[0]).toMatchObject({ label: 'Time', value: '2026-06-16 00:00 UTC' });
    expect(state.checkpointSummary).toMatchObject({ label: 'Latest checkpoint', detail: 'checkpoints/session.json' });
    expect(state.rpgJobs).toHaveLength(1);
    expect(state.rpgAssets).toHaveLength(1);
    expect(state.rpgReports).toHaveLength(1);
    expect(state.jobCards[0]).toMatchObject({ id: 'job:rpg', progress: 25, source: 'live', title: 'rpg.turn' });
  });

  it('derives player rail content from live session state when available', () => {
    const inventory = {
      sessions: [
        {
          session_id: 'player-live',
          title: 'Player state campaign',
          updated_at: '2026-06-16T00:00:00Z',
          state: {
            player: {
              name: 'Mira Vale',
              level: 4,
              class: 'Scout',
              background: 'Caravan outrider',
              hp: { current: 42, max: 50 },
              stamina: { current: 31, max: 40 },
              mana: { current: 8, max: 20 },
              xp: 350,
              xp_to_next: 500,
              currency: { gold: 17, silver: 5, copper: 2 },
              reputation: { label: 'Trusted', score: 18 },
              equipment: [{ name: 'Shortbow', slot: 'weapon' }],
              inventory: { items: [{ name: 'Ration', quantity: 3 }] },
            },
            party: [{ name: 'Bran', role: 'Innkeeper', level: 2, hp: 18, max_hp: 22 }],
            quests: [{ title: 'Find the Quarry Trail', objective: 'Ask Bran about the old quarry road.', status: 'active' }],
          },
        },
      ],
      diagnostics: [],
    } as PersistenceInventory;

    const state = createRpgWorkspaceState({ inventory, selectedSessionId: 'player-live' });

    expect(state.heroSummary).toMatchObject({
      source: 'live',
      avatar: 'M',
      name: 'Mira Vale',
      subtitle: 'Level 4 • Scout',
      origin: 'Caravan outrider',
      xpLabel: '350 / 500',
      xpPercent: 70,
      gold: '17g 5s 2c',
      renown: 'Trusted',
    });
    expect(state.heroStats).toEqual([
      { label: 'HP', value: '42 / 50', percent: 84, tone: 'danger' },
      { label: 'Stamina', value: '31 / 40', percent: 78, tone: 'success' },
      { label: 'Mana', value: '8 / 20', percent: 40, tone: 'mana' },
    ]);
    expect(state.equippedGear[0]).toMatchObject({ name: 'Shortbow', slot: 'Weapon' });
    expect(state.partyMembers[0]).toMatchObject({ avatar: 'B', name: 'Bran', role: 'Lv. 2 Innkeeper', hp: '18 / 22', percent: 82 });
    expect(state.activeQuests[0]).toMatchObject({ title: 'Find the Quarry Trail', detail: 'Ask Bran about the old quarry road.' });
    expect(state.inventoryItems[0]).toMatchObject({ label: 'Ration', count: '3' });
  });

  it('derives world rail, encounter, and NPC relationship state from live sessions', () => {
    const inventory = {
      sessions: [
        {
          session_id: 'world-live',
          title: 'World rail campaign',
          location: 'Old Quarry Road',
          updated_at: '2026-06-16T00:00:00Z',
          state: {
            world: {
              time: 'Day 3 • Dusk',
              weather: 'Rain, fog',
              temperature: 4,
            },
            player: {
              name: 'Mira Vale',
              reputation: { label: 'Trusted', score: 61 },
            },
            relationships: [
              { name: 'Bran', stance: 'Ally', score: 82 },
              { name: 'Captain Aldric', trust: 0.45 },
            ],
            encounter: {
              status: 'active',
              title: 'Bandit ambush',
              enemies: [{ name: 'Road bandit' }, { name: 'Lookout' }],
            },
          },
        },
      ],
      diagnostics: [],
    } as PersistenceInventory;

    const state = createRpgWorkspaceState({ inventory, selectedSessionId: 'world-live' });

    expect(state.worldStateRows).toEqual([
      { icon: '☀', label: 'Time', value: 'Day 3 • Dusk' },
      { icon: '≋', label: 'Weather', value: 'Rain, fog' },
      { icon: '❄', label: 'Temperature', value: '4°C' },
      { icon: '✦', label: 'Reputation', value: 'Trusted' },
    ]);
    expect(state.npcRelationships).toEqual([
      { name: 'Bran', stance: 'Ally', score: 82 },
      { name: 'Captain Aldric', stance: 'Neutral', score: 45 },
    ]);
    expect(state.encounter).toMatchObject({ icon: '⚔', source: 'live', title: 'Bandit ambush', detail: 'Combatants: Road bandit, Lookout' });
  });

  it('derives narrative events and journal entries from live session timeline records', () => {
    const inventory = {
      sessions: [
        {
          session_id: 'story-live',
          title: 'Narrative campaign',
          location: 'Rusty Flagon Tavern',
          updated_at: '2026-06-16T01:00:00Z',
          turn_count: 9,
          state: {
            recent_events: [
              {
                turn: 9,
                type: 'dialogue',
                actor: 'Bran',
                text: 'The quarry road has been quiet since midnight.',
              },
              {
                turn: 8,
                type: 'discovery',
                title: 'Found a torn crest',
                summary: 'A muddy crest from the old quarry company was found beside the tavern door.',
              },
            ],
          },
        },
      ],
      diagnostics: [],
    } as PersistenceInventory;

    const state = createRpgWorkspaceState({ inventory, selectedSessionId: 'story-live' });

    expect(state.selectedSessionSummary.summary).toBe('The quarry road has been quiet since midnight.');
    expect(state.recentEvents).toEqual([
      'Bran: The quarry road has been quiet since midnight.',
      'A muddy crest from the old quarry company was found beside the tavern door.',
    ]);
    expect(state.journalEntries[0]).toMatchObject({ time: 'Turn 9', title: 'dialogue', detail: 'The quarry road has been quiet since midnight.' });
    expect(state.journalDetail).toMatchObject({ title: 'dialogue', detail: 'The quarry road has been quiet since midnight.' });
    expect(state.journalDetail.tags).toEqual(['Live session', 'Dialogue', 'Replay-safe']);
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
