import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CharacterManagementPanel } from './CharacterManagementPanel';

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><CharacterManagementPanel /></QueryClientProvider>);
}

const character = {
  id: 'maya', display_name: 'Maya', description: 'Easygoing',
  personality_prompt: 'Be warm and easygoing.', default_greeting: 'Hey.',
  default_voice_asset_id: 'voice-cloning:maya', speech_style: {}, identity_policy: {},
  shared_memory_policy: {}, active_version: 2, enabled: true, status: 'active',
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
};

const data = {
  character,
  versions: [{ character_id: 'maya', version: 2, personality_prompt: 'Be warm.', created_at: '2026-01-02T00:00:00Z' }],
  memories: [{ id: 'memory:one', category: 'relationship', scope: 'global', content: 'Rainy hike joke.', pinned: false, revision: 1 }],
  pending_suggestions: [{ id: 'candidate:one', proposed_category: 'fact', proposed_content: 'User likes tea.', confidence: 0.9, created_at: '2026-01-02T00:00:00Z' }],
  sessions: [{ id: 'chat:one', title: 'Maya call', message_count: 4, character_message_count: 3, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z' }],
  generated_at: '2026-01-02T00:00:00Z',
};

afterEach(() => vi.unstubAllGlobals());

describe('CharacterManagementPanel', () => {
  it('shows profile and owned backend data', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input.toString(), 'http://localhost').pathname;
      if (path === '/api/characters') return Response.json({ characters: [character] });
      if (path === '/api/characters/maya/data') return Response.json(data);
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
      const path = new URL(input.toString(), 'http://localhost').pathname;
      if (path === '/api/characters') return Response.json({ characters: [character] });
      if (path === '/api/characters/maya/data' && init?.method === 'POST') return new Response('not found', { status: 404 });
      if (path === '/api/characters/maya/data') return Response.json(data);
      if (path === '/api/characters/maya/data/actions') {
        actionBodies.push(JSON.parse(String(init?.body)));
        return Response.json({
          ok: true, character_id: 'maya', deleted_memory_records: 1,
          deleted_memory_candidates: 1, deleted_memory_snapshots: 1,
          deleted_transcript_messages: 0, voice_unlinked: false, profile_archived: false,
        });
      }
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
