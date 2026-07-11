import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { liveConversationStore } from '../assistant-workspace/live-conversation-store';
import {
  LiveChatPanel,
  invokeExistingLiveCallControl,
  readLiveCallSnapshot,
} from './LiveChatPanel';

const defaultProfile = {
  presence_preset: 'natural', talkativeness: 50, conversation_stance: 'automatic',
  conversation_pace: 'balanced', interruption_preference: 'balanced', assistant_backchannel_mode: 'off',
  initiative_mode: 'gentle', idle_threshold_ms: 15000, long_pause_behavior: 'wait',
  response_length: 'conversational', response_onset_style: 'adaptive', emotional_attunement: 'subtle',
  topic_continuity: 'natural', max_idle_prompts: 1, duplex_mode: 'automatic',
  pronunciation_save_policy: 'ask', profile_version: 1,
};

beforeEach(() => {
  window.localStorage.clear();
  liveConversationStore.reset();
  window.localStorage.setItem('omnix.liveConversation.serverProfileMigrated.v1', 'done');
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = input.toString();
    if (url === '/api/characters') return Response.json({ characters: [] });
    if (url.includes('/interaction')) {
      return Response.json({
        id: 'chat:one', title: 'Test chat', interaction_mode: 'system', character_id: null,
        voice_asset_id: null, read_memory: false, write_memory: false,
        shared_memory_access: 'none', transcript_policy: 'persistent', messages: [],
      });
    }
    if (url.includes('/live-conversation/pronunciations')) {
      return Response.json({ session_id: 'chat:one', entries: [] });
    }
    return Response.json(defaultProfile);
  }));
});

afterEach(() => {
  document.body.innerHTML = '';
  liveConversationStore.reset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderPanel(sessionId: string | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LiveChatPanel sessionId={sessionId} />
    </QueryClientProvider>,
  );
}

describe('LiveChatPanel', () => {
  it('uses user defaults when no chat session is selected', async () => {
    renderPanel(null);
    expect(screen.getByRole('heading', { name: 'Live Chat' })).toBeInTheDocument();
    expect(screen.getByText('Select a Chat session')).toBeInTheDocument();
    expect(await screen.findByLabelText('Presence')).toHaveValue('natural');
    expect(screen.getByText('Select a Chat session before saving pronunciation guidance.')).toBeInTheDocument();
  });

  it('renders identity, floor, and status from the authoritative store', () => {
    liveConversationStore.dispatch({ type: 'identity', identity: { characterId: 'maya', displayName: 'Maya' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'user_turn', value: 'speaking' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'floor_owner', value: 'user' } });
    liveConversationStore.dispatch({
      type: 'duplex',
      duplex: { resolvedMode: 'echo_aware', reason: 'calibration_confident', confidence: 0.9 },
    });

    renderPanel('chat:one');
    expect(screen.getByText('Call connected')).toBeInTheDocument();
    expect(screen.getByText('Maya is listening')).toBeInTheDocument();
    expect(screen.getByText('Echo-aware barge-in')).toBeInTheDocument();
    expect(screen.getByText('user')).toBeInTheDocument();
  });

  it('reuses the existing live-call control instead of creating another voice pipeline', () => {
    const card = document.createElement('section');
    card.className = 'assistant-live-card';
    card.innerHTML = `
      <span class="assistant-live-identity">Talking to Maya</span>
      <div class="assistant-live-state"><span>Listening</span></div>
      <button type="button">Start Call</button>
    `;
    document.body.appendChild(card);
    const click = vi.spyOn(card.querySelector('button')!, 'click');

    expect(readLiveCallSnapshot()).toMatchObject({
      connected: false,
      state: 'Listening',
      identity: 'Talking to Maya',
    });
    expect(invokeExistingLiveCallControl()).toBe(true);
    expect(click).toHaveBeenCalledTimes(1);
  });
});
