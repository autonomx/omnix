import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LiveConversationControls } from './LiveConversationControls';
import type { LiveConversationProfile } from './liveConversationProfileClient';

const profile: LiveConversationProfile = {
  presence_preset: 'natural',
  talkativeness: 50,
  conversation_stance: 'automatic',
  conversation_pace: 'balanced',
  interruption_preference: 'balanced',
  assistant_backchannel_mode: 'off',
  initiative_mode: 'gentle',
  idle_threshold_ms: 15000,
  long_pause_behavior: 'wait',
  response_length: 'conversational',
  response_onset_style: 'adaptive',
  emotional_attunement: 'subtle',
  topic_continuity: 'natural',
  max_idle_prompts: 1,
  duplex_mode: 'automatic',
  pronunciation_save_policy: 'ask',
  profile_version: 1,
};

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('LiveConversationControls', () => {
  it('renders the effective server profile and advanced turn-taking controls', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      user_defaults: profile,
      session_override: null,
      effective: profile,
      source: 'user_defaults',
    })));

    render(<LiveConversationControls sessionId="chat:one" />);

    expect(await screen.findByLabelText('Presence')).toHaveValue('natural');
    expect(screen.getByLabelText('Conversation stance')).toHaveValue('automatic');
    expect(screen.getByLabelText('Response length')).toHaveValue('conversational');
    fireEvent.click(screen.getByRole('button', { name: 'Show advanced controls' }));
    expect(screen.getByLabelText('Conversation pace')).toHaveValue('balanced');
    expect(screen.getByLabelText('Assistant listener backchannels')).toHaveValue('off');
    expect(screen.getByLabelText('Response onset')).toHaveValue('adaptive');
    expect(screen.getByLabelText('Emotional attunement')).toHaveValue('subtle');
    expect(screen.getByLabelText('Topic continuity')).toHaveValue('natural');
    expect(screen.getByLabelText('Pronunciation saving')).toHaveValue('ask');
    expect(screen.getByLabelText('First idle prompt seconds')).toHaveAttribute('min', '1');
  });

  it('never writes the defaults on load, even when this browser has settings of its own', async () => {
    // A private window (the launcher's "Open app privately") starts with empty storage, and copying its fresh
    // settings to the server put the person's defaults back to Balanced on every launch.
    window.localStorage.setItem('omnix.chatbot.assistantSettings', JSON.stringify({ conversationPace: 'balanced' }));
    window.localStorage.setItem('omnix.liveConversation.settings', JSON.stringify({ conversationPace: 'balanced' }));
    const requests = stubProfileServer(null);

    render(<LiveConversationControls sessionId="chat:one" />);
    await screen.findByLabelText('Presence');

    expect(requests.map((request) => request.init?.method)).toEqual(['GET']);
  });

  it("saves a change as the person's setting, so the next chat starts with it", async () => {
    const requests = stubProfileServer(null);

    render(<LiveConversationControls sessionId="chat:one" />);
    await screen.findByLabelText('Presence');
    fireEvent.change(screen.getByLabelText('Presence'), { target: { value: 'engaged' } });

    expect(await screen.findByRole('status')).toHaveTextContent('Saved as your Live Chat settings.');
    const writes = requests.filter((request) => request.init?.method && request.init.method !== 'GET');
    expect(writes.map((request) => `${request.init?.method} ${request.url}`)).toEqual(['PATCH /api/live-chat/profile/defaults']);
    expect(JSON.parse(String(writes[0]?.init?.body))).toEqual({ presence_preset: 'engaged' });
    expect(screen.getByLabelText('Presence')).toHaveValue('engaged');
    expect(JSON.parse(window.localStorage.getItem('omnix.liveConversation.settings') || '{}')).toEqual({
      conversationPace: 'balanced',
      interruptionPreference: 'balanced',
      backchannelMode: 'off',
    });
  });

  it('applies the full-duplex profile as one patch, and a chat with its own override follows it', async () => {
    const requests = stubProfileServer({ ...profile, duplex_mode: 'half_duplex', profile_version: 9 });

    render(<LiveConversationControls sessionId="chat:one" />);
    fireEvent.click(await screen.findByRole('button', { name: /Full duplex/ }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Full duplex/ })).toHaveAttribute('aria-pressed', 'true');
    });
    const writes = requests.filter((request) => request.init?.method && request.init.method !== 'GET');
    expect(writes.map((request) => `${request.init?.method} ${request.url}`)).toEqual([
      'PATCH /api/live-chat/profile/defaults',
      'DELETE /api/chat/sessions/chat%3Aone/live-conversation/profile',
    ]);
    const patch = JSON.parse(String(writes[0]?.init?.body));
    expect(patch).toMatchObject({
      conversation_pace: 'quick',
      interruption_preference: 'easy',
      assistant_backchannel_mode: 'natural',
      duplex_mode: 'echo_aware',
      response_onset_style: 'immediate',
    });
    expect(Object.keys(patch)).toHaveLength(16);
    expect(screen.getByText('User defaults')).toBeInTheDocument();
  });
});

function envelope(defaults: LiveConversationProfile, override: LiveConversationProfile | null = null) {
  return {
    user_defaults: defaults,
    session_override: override,
    effective: override ?? defaults,
    source: override ? 'session_override' : 'user_defaults',
  };
}

// The gateway's profile routes over one in-memory store: defaults, and this chat's override (or none).
function stubProfileServer(initialOverride: LiveConversationProfile | null) {
  let defaults = profile;
  let override = initialOverride;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? new URL(input.url).pathname : input.toString();
    const method = init?.method ?? (input instanceof Request ? input.method : 'GET');
    const body = init?.body ?? (input instanceof Request && method !== 'GET' ? await input.clone().text() : undefined);
    requests.push({ url, init: { ...init, method, body } });
    if (url === '/api/live-chat/profile/defaults') {
      if (method === 'PATCH') defaults = { ...defaults, ...JSON.parse(String(body)), profile_version: defaults.profile_version + 1 };
      return Response.json(defaults);
    }
    if (method === 'DELETE') override = null;
    return Response.json(envelope(defaults, override));
  }));
  return requests;
}
