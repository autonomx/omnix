import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { CharacterManagementPanel } from './CharacterManagementPanel';

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <CharacterManagementPanel />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

const legacyCharacter = {
  id: 'maya',
  display_name: 'Maya',
  description: 'Easygoing',
  personality_prompt: 'Be warm and easygoing.',
  default_greeting: 'Hey.',
  default_voice_asset_id: 'voice-cloning:maya',
  speech_style: {},
  identity_policy: {},
  shared_memory_policy: {},
  active_version: 2,
  enabled: true,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const legacyData = {
  character: legacyCharacter,
  versions: [{ character_id: 'maya', version: 2, personality_prompt: 'Be warm.', created_at: '2026-01-02T00:00:00Z' }],
  memories: [{ id: 'memory:one', category: 'relationship', scope: 'global', content: 'Rainy hike joke.', pinned: false, revision: 1 }],
  pending_suggestions: [{ id: 'candidate:one', proposed_category: 'fact', proposed_content: 'User likes tea.', confidence: 0.9, created_at: '2026-01-02T00:00:00Z' }],
  sessions: [{ id: 'chat:one', title: 'Maya call', message_count: 4, character_message_count: 3, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z' }],
  generated_at: '2026-01-02T00:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('CharacterManagementPanel dashboard', () => {
  it('renders the production character dashboard sections and precise viseme strip', async () => {
    const character = {
      id: 'character:maya',
      display_name: 'Maya',
      description: 'Calm conversational companion.',
      personality_prompt: 'Be warm, curious, and supportive.',
      default_greeting: 'Hi, I am Maya.',
      default_voice_asset_id: 'voice-profile-maya',
      speech_style: {},
      identity_policy: {},
      shared_memory_policy: {},
      active_version: 3,
      enabled: true,
      status: 'active',
      created_at: '2026-07-10T00:00:00Z',
      updated_at: '2026-07-10T00:00:00Z',
    };
    const pack = {
      character_id: character.id,
      version: 2,
      render_mode: 'viseme',
      renderer: 'sprite',
      rig_asset_id: null,
      base_asset_id: 'image-maya-base',
      mouth_frames: {
        closed: 'image-maya-closed',
        A: 'image-maya-a',
        E: 'image-maya-e',
        O: 'image-maya-o',
        U: 'image-maya-u',
        MBP: 'image-maya-mbp',
        FV: 'image-maya-fv',
        L: 'image-maya-l',
        WQ: 'image-maya-wq',
        other: 'image-maya-other',
      },
      blink_frames: {},
      expression_frames: {},
      outfit_frames: {},
      background_asset_ids: {},
      active_outfit: null,
      active_background: null,
      mouth_anchor: {},
      created_at: '2026-07-10T00:00:00Z',
      updated_at: '2026-07-10T00:00:00Z',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/characters') return Response.json({ characters: [character] });
      if (path === '/api/characters/character%3Amaya/data') return Response.json({
        character,
        versions: [{ character_id: character.id, version: 3, personality_prompt: character.personality_prompt, created_at: character.created_at }],
        memories: [{ id: 'memory-1', category: 'relationship', scope: 'character', content: 'Prefers quiet conversations.', pinned: false, revision: 1 }],
        pending_suggestions: [{ id: 'suggestion-1', proposed_category: 'preference', proposed_content: 'Likes stargazing.', confidence: 0.8, created_at: character.created_at }],
        sessions: [{ id: 'session-1', title: 'Hello Maya', message_count: 4, character_message_count: 2, created_at: character.created_at, updated_at: character.updated_at }],
        generated_at: character.updated_at,
      });
      if (path === '/api/characters/character%3Amaya/avatar-pack') return Response.json(pack);
      if (path === '/api/voice-profiles/voice-profile-maya/governance') return Response.json({
        asset_id: 'voice-profile-maya',
        subject_owner: 'Maya',
        source_type: 'user_recording',
        source_reference: 'local',
        creator_id: 'local-user',
        consent_status: 'granted',
        consent_recorded_at: '2026-07-10T00:00:00Z',
        allowed_uses: ['character', 'live_call'],
        source_sha256: 'a'.repeat(64),
        deletion_state: 'active',
        deletion_reason: '',
        updated_at: '2026-07-10T00:00:00Z',
      });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPanel();

    expect(await screen.findByRole('heading', { name: 'Character profile' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Voice governance' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Live avatar' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cloned-voice backfill' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Character data / relationship data' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Danger zone / cleanup' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search characters')).toBeInTheDocument();
    expect(await screen.findByAltText('Maya avatar preview')).toBeInTheDocument();
    expect(screen.getByText('Viseme support (9 mouth shapes)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create characters from cloned voices' })).toBeInTheDocument();
  });

  it('shows profile and owned backend data', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/characters') return Response.json({ characters: [legacyCharacter] });
      if (path === '/api/characters/maya/data') return Response.json(legacyData);
      return new Response('not found', { status: 404 });
    }));

    renderPanel();

    expect(await screen.findByRole('button', { name: /Maya/ })).toBeInTheDocument();
    expect(await screen.findByText('Rainy hike joke.')).toBeInTheDocument();
    expect(screen.getByText('User likes tea.')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('requires typed confirmation and sends independent cleanup choices', async () => {
    const actionBodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/characters') return Response.json({ characters: [legacyCharacter] });
      if (path === '/api/characters/maya/data/actions') {
        actionBodies.push(JSON.parse(String(init?.body)));
        return Response.json({
          ok: true,
          character_id: 'maya',
          deleted_memory_records: 1,
          deleted_memory_candidates: 1,
          deleted_memory_snapshots: 1,
          deleted_transcript_messages: 0,
          voice_unlinked: false,
          profile_archived: false,
        });
      }
      if (path === '/api/characters/maya/data') return Response.json(legacyData);
      return new Response('not found', { status: 404 });
    }));

    renderPanel();
    await screen.findByRole('button', { name: /Maya/ });
    fireEvent.click(screen.getByLabelText('Delete character memories and pending suggestions'));
    const apply = screen.getByRole('button', { name: 'Apply selected actions' });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Confirm character id'), { target: { value: 'maya' } });
    fireEvent.click(apply);

    await waitFor(() => expect(actionBodies).toHaveLength(1));
    expect(actionBodies[0]).toMatchObject({
      confirm_character_id: 'maya',
      delete_memories: true,
      delete_transcripts: false,
      unlink_voice: false,
      archive_profile: false,
    });
  });
});
