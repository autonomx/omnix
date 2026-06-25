import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { RpgWorkspace } from './RpgWorkspace';

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

function renderRpg() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'rpg');

  if (!module) {
    throw new Error('RPG module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <RpgWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('RpgWorkspace campaign handoff', () => {
  it('keeps a created campaign selected before inventory catches up', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        return Response.json({
          sessions: [
            {
              session_id: 'rpg-previous-1',
              title: 'Previous Campaign',
              location: 'Old Road',
              summary: 'The previous campaign is still selected.',
              turn_count: 4,
              updated_at: '2026-06-19T00:00:00Z',
            },
          ],
          diagnostics: [],
        });
      }

      if (path === '/api/rpg/sessions/rpg-previous-1') {
        return Response.json({
          ok: true,
          session_id: 'rpg-previous-1',
          session: {
            session_id: 'rpg-previous-1',
            title: 'Previous Campaign',
            location: 'Old Road',
            timeline: [{ title: 'Old conversation', detail: 'Bran remembers the previous campaign.' }],
          },
        });
      }

      if (path === '/api/rpg/new-game' && init?.method === 'POST') {
        return Response.json({
          ok: true,
          session_id: 'rpg-created-lagging',
          status: 'ready',
          session: {
            session_id: 'rpg-created-lagging',
            title: 'Created Campaign',
            location: 'Rusty Flagon Tavern',
            summary: 'A fresh campaign begins at the tavern.',
            turn_count: 0,
            state: {
              player: { name: 'Elara' },
              timeline: [{ title: 'Campaign begins', detail: 'Elara enters the Rusty Flagon Tavern.' }],
            },
          },
        });
      }

      if (path === '/api/jobs') {
        return Response.json({
          jobs: [
            {
              id: 'job:old-turn',
              module: 'rpg',
              type: 'rpg.turn',
              status: 'completed',
              resource_class: 'gpu:llm',
              priority: 0,
              stages: [],
              input_ref: { session_id: 'rpg-previous-1' },
              input_payload: { command: 'i ask bran how business is going' },
              output_refs: [{ type: 'rpg_turn_response', content: 'Bran talks about the old campaign business.' }],
              created_at: '2026-06-19T00:00:01Z',
              updated_at: '2026-06-19T00:00:04Z',
              completed_at: '2026-06-19T00:00:04Z',
            },
          ],
        });
      }

      if (path === '/api/assets') return Response.json({ assets: [] });
      if (path === '/api/reports') return Response.json({ reports: [] });

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderRpg();

    expect(await screen.findByText('i ask bran how business is going')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    fireEvent.click(screen.getByRole('button', { name: /^New Campaign/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Create Campaign' }));

    expect(await screen.findByRole('dialog', { name: 'Campaign Ready' })).toBeInTheDocument();
    expect(screen.getByLabelText('Session')).toHaveValue('rpg-created-lagging');
    expect(screen.queryByText('i ask bran how business is going')).not.toBeInTheDocument();
    expect(screen.queryByText('Bran talks about the old campaign business.')).not.toBeInTheDocument();
    expect((await screen.findAllByText('Elara enters the Rusty Flagon Tavern.')).length).toBeGreaterThan(0);
  });

  it('surfaces a created campaign and queues the first turn for it', async () => {
    let inventoryReads = 0;
    let turnApplied = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        inventoryReads += 1;
        return Response.json({
          sessions: inventoryReads > 1
            ? [
                  {
                    session_id: 'rpg-created-1',
                    title: 'Created Campaign',
                    location: 'Rusty Flagon Tavern',
                    summary: 'A new campaign is ready at the tavern.',
                    turn_count: 0,
                    updated_at: '2026-06-20T00:00:00Z',
                  },
                ]
            : [
                {
                  session_id: 'rpg-previous-1',
                  title: 'Previous Campaign',
                  location: 'Old Road',
                  summary: 'The previous campaign is still selected.',
                  turn_count: 4,
                  updated_at: '2026-06-19T00:00:00Z',
                  timeline: [{ title: 'Old conversation', detail: 'Bran speaks from the previous campaign.', turn: 4 }],
                },
              ],
          diagnostics: [],
        });
      }

      if (path === '/api/rpg/new-game' && init?.method === 'POST') {
        return Response.json({
          ok: true,
          session_id: 'rpg-created-1',
          status: 'ready',
          session: {
            manifest: { session_id: 'rpg-created-1', title: 'Created Campaign' },
            state: {
              ability_tree: {
                abilities: [{ ability_id: 'recon_aimed_shot', icon: '✦', name: 'Aimed Shot' }],
              },
              encounter: { status: 'inactive', title: 'No active combat', summary: 'All quiet for now.' },
              environment_snapshot: {
                display: { day_time: 'Day 1', weather: 'Clear' },
                context: { location_label: 'Rusty Flagon Tavern' },
                region_id: 'market_road',
              },
              hotbar: { 1: 'recon_aimed_shot' },
              party: [],
              player: {
                name: 'Elara',
                level: 1,
                class: 'Frontier Scout',
                background: 'Wanderer',
                currency: { gold: 0 },
                equipment: [{ name: 'Travel cloak', slot: 'clothing' }],
                inventory: [{ name: 'Trail rations', quantity: 3 }],
                renown: 'Unknown (0)',
                resources: {
                  hp: { current: 92, max: 92 },
                  stamina: { current: 91, max: 91 },
                  mana: { current: 30, max: 30 },
                },
                xp: { current: 0, max: 100 },
              },
              quests: [{ title: 'Rumor at the Rusty Flagon', status: 'active', objective: 'Ask Bran which rumor is true.' }],
              quick_actions: ['Talk to Bran'],
              relationships: [],
              timeline: [{ title: 'Campaign begins', detail: 'Elara enters the Rusty Flagon Tavern.', turn: 0 }],
            },
          },
        });
      }

      if (path === '/api/rpg/sessions/rpg-created-1/turn' && init?.method === 'POST') {
        turnApplied = true;
        return Response.json({
          ok: true,
          session_id: 'rpg-created-1',
          command: 'I ask Bran how he is.',
          response: 'Bran smiles and says he is well.',
          content: 'Bran smiles and says he is well.',
          session: {
            manifest: { session_id: 'rpg-created-1', title: 'Created Campaign' },
            state: {
              timeline: [
                { title: 'Campaign begins', detail: 'Elara enters the Rusty Flagon Tavern.', turn: 0 },
                { title: 'Turn request', detail: 'I ask Bran how he is.', turn: 1 },
                { title: 'Bran', detail: 'Bran smiles and says he is well.', turn: 1 },
              ],
            },
          },
        });
      }

      if (path === '/api/jobs') {
        return Response.json({
          jobs: turnApplied
            ? [
                {
                  id: 'foreground:rpg.turn:1',
                  module: 'rpg',
                  type: 'rpg.turn',
                  status: 'completed',
                  resource_class: 'gpu:llm',
                  priority: 0,
                  stages: [],
                  input_ref: { session_id: 'rpg-created-1' },
                  input_payload: { command: 'I ask Bran how he is.' },
                  output_refs: [{ type: 'rpg_turn_response', content: 'Bran smiles and says he is well.' }],
                  created_at: '2026-06-20T00:00:01Z',
                  updated_at: '2026-06-20T00:00:04Z',
                  completed_at: '2026-06-20T00:00:04Z',
                },
              ]
            : [],
        });
      }

      if (path === '/api/assets') {
        return Response.json({ assets: [] });
      }

      if (path === '/api/reports') {
        return Response.json({ reports: [] });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderRpg();

    expect(await screen.findByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    expect((await screen.findAllByText('Bran speaks from the previous campaign.')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    fireEvent.click(screen.getByRole('button', { name: /^New Campaign/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Create Campaign' }));

    expect(await screen.findByRole('dialog', { name: 'Campaign Ready' })).toBeInTheDocument();
    expect(screen.queryByText('Bran speaks from the previous campaign.')).not.toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Created Campaign — rpg-created-1' })).toBeInTheDocument();
    expect(await screen.findByText('Created Campaign')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Elara' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Alyndra' })).not.toBeInTheDocument();
    expect(screen.getByText('0 / 4')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Thorin Ironfist' })).not.toBeInTheDocument();
    const playerRail = screen.getByRole('complementary', { name: 'Player, party, and quests' });
    expect(within(playerRail).getByText('Travel cloak')).toBeInTheDocument();
    expect(within(playerRail).getByText('Rumor at the Rusty Flagon')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trail rations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Talk' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Aimed Shot' }).length).toBeGreaterThan(0);
    expect(screen.getByText('No NPC relationships recorded.')).toBeInTheDocument();
    expect(screen.getByText('No active RPG jobs')).toBeInTheDocument();
    expect(screen.getByText('market_road')).toBeInTheDocument();
    expect(screen.getAllByText('Elara enters the Rusty Flagon Tavern.').length).toBeGreaterThan(0);
    expect(document.querySelector('img[src="/rpg/hero-alyndra.svg"]')).not.toBeInTheDocument();
    expect(document.querySelector('img[src="/rpg/glimmerdeep-pass-scene.svg"]')).not.toBeInTheDocument();
    expect(document.querySelector('img[src="/rpg/glimmerdeep-pass-map.svg"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Enter World' }));

    await waitFor(() => {
      const commandInput = screen.getByLabelText('Command') as HTMLTextAreaElement;
      expect(commandInput.value).toBe('');
    });

    fireEvent.change(screen.getByLabelText('Command'), { target: { value: 'I ask Bran how he is.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue RPG turn' }));

    await waitFor(() => {
      const turnCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input as RequestInfo | URL) === '/api/rpg/sessions/rpg-created-1/turn' &&
          init?.method === 'POST',
      );
      expect(String(turnCall?.[1]?.body)).toContain('"command":"I ask Bran how he is."');
    });
    expect(screen.getByText('Elara (You)')).toBeInTheDocument();
    expect(screen.getByText('Bran')).toBeInTheDocument();
    const storyScene = screen.getByRole('region', { name: /Rusty Flagon Tavern/ });
    expect(within(storyScene).getByText('I ask Bran how he is.')).toBeInTheDocument();
    expect(within(storyScene).getByText('Bran smiles and says he is well.')).toBeInTheDocument();
  });
});
