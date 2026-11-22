 
/* eslint-disable no-restricted-syntax -- baseline WP-9.x */
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { liveConversationStore } from '../workspace/live-conversation-store';
import { LiveChatPanel, resetLiveChatTabForTests } from './LiveChatPanel';
import { createTestQueryClient } from '../../../test/renderWithProviders';

const defaultProfile = {
  presence_preset: 'natural', talkativeness: 50, conversation_stance: 'automatic',
  conversation_pace: 'balanced', interruption_preference: 'balanced', assistant_backchannel_mode: 'off',
  initiative_mode: 'gentle', idle_threshold_ms: 15000, long_pause_behavior: 'wait',
  response_length: 'conversational', response_onset_style: 'adaptive', emotional_attunement: 'subtle',
  topic_continuity: 'natural', max_idle_prompts: 1, quiet_hours_enabled: false, quiet_hours_start: '22:00', quiet_hours_end: '08:00', max_initiatives_per_hour: 4, duplex_mode: 'automatic',
  pronunciation_save_policy: 'ask', profile_version: 1,
};

let savedProfiles: unknown[] = [];

beforeEach(() => {
  window.localStorage.clear();
  liveConversationStore.reset();
  resetLiveChatTabForTests();
  savedProfiles = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? new URL(input.url).pathname : input.toString();
    if (url.endsWith('/api/settings/profile')) {
      const method = input instanceof Request ? input.method : init?.method ?? 'GET';
      if (method === 'POST') {
        savedProfiles.push(await (input instanceof Request ? input.json() : JSON.parse(String(init?.body))));
        return Response.json({ success: true });
      }
      return Response.json({ settings: { settings_control_center: { assistant: { livePortraitEngine: 'float' } } } });
    }
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

function renderPanel(sessionId: string | null, onToggleCall = vi.fn()) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <LiveChatPanel sessionId={sessionId} onToggleCall={onToggleCall} />
    </QueryClientProvider>,
  );
}

function openTab(name: string): void {
  fireEvent.click(screen.getByRole('tab', { name }));
}

describe('LiveChatPanel', () => {
  it('shows one section at a time, as tabs, starting with the character', () => {
    renderPanel('chat:one');
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Character', 'Presence', 'Voice', 'Video', 'Call']);
    expect(screen.getByRole('tab', { name: 'Character' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('button', { name: 'Start Call' })).toBeNull();

    openTab('Call');
    expect(screen.getByRole('tab', { name: 'Call' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'live-chat-tab-call');
    expect(screen.getByRole('button', { name: 'Start Call' })).toBeInTheDocument();
  });

  it('keeps the open tab when the page is opened again', () => {
    const first = renderPanel('chat:one');
    openTab('Voice');
    first.unmount();

    renderPanel('chat:one');
    expect(screen.getByRole('tab', { name: 'Voice' })).toHaveAttribute('aria-selected', 'true');
  });

  it('uses user defaults when no chat session is selected', async () => {
    renderPanel(null);
    expect(screen.getByRole('heading', { name: 'Live Chat' })).toBeInTheDocument();
    expect(screen.getByText('Select a Chat session')).toBeInTheDocument();
    openTab('Presence');
    await waitFor(() => expect(screen.getByLabelText('Presence', { selector: 'select' })).toHaveValue('natural'));
    openTab('Voice');
    expect(screen.getByText('Select a Chat session before saving pronunciation guidance.')).toBeInTheDocument();
  });

  it('chooses the live portrait engine on the Video tab, saving it to the settings profile', async () => {
    renderPanel('chat:one');
    openTab('Video');

    const float = await screen.findByRole('button', { name: /^FLOAT/ });
    await waitFor(() => expect(float).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(screen.getByRole('button', { name: /^FlashHead Lite/ }));

    await waitFor(() => expect(screen.getByRole('button', { name: /^FlashHead Lite/ })).toHaveAttribute('aria-pressed', 'true'));
    expect(savedProfiles).toEqual([
      expect.objectContaining({ settings_profile_patch: { assistant: expect.objectContaining({ livePortraitEngine: 'flashhead-lite' }) } }),
    ]);
    expect(screen.getByText('Saved. The next call uses this engine.')).toBeInTheDocument();
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
    openTab('Call');
    expect(screen.getByText('Call connected')).toBeInTheDocument();
    expect(screen.getByText('Maya is listening')).toBeInTheDocument();
    expect(screen.getByText('Echo-aware barge-in')).toBeInTheDocument();
    expect(screen.getByText('user')).toBeInTheDocument();
  });

  it('starts the call through Chat instead of creating another voice pipeline', () => {
    const onToggleCall = vi.fn();
    renderPanel('chat:one', onToggleCall);
    openTab('Call');

    fireEvent.click(screen.getByRole('button', { name: 'Start Call' }));

    expect(onToggleCall).toHaveBeenCalledOnce();
    expect(screen.getByText('Starting live call…')).toBeInTheDocument();
  });
});
