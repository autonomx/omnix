import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../../test/renderWithProviders';
import { liveCallPresentationStore } from '../workspace/live-call-presentation-store';
import { liveConversationStore } from '../workspace/live-conversation-store';
import { stopLiveVoice } from '../workspace/live-voice-session-lifecycle';
import type { LiveConversationProfile } from './liveConversationProfileClient';
import { callSceneStore, type CallSceneMember, type CallSceneView } from '../workspace/live-call-scene';
import { characterClient } from './characterClient';
import { liveChatMessagesFor, sceneSpeakerName } from './chatMessageModel';
import { LiveCallScene } from './LiveCallScene';

const SCENE_PATH = '/api/chat/sessions/s1/scene';
const HOST = { character_id: 'mara', display_name: 'Mara Quinn', role: 'host', seat: 0 } as CallSceneMember;
const BEA = { character_id: 'bea', display_name: 'Bea Hart', role: 'guest', seat: 1 } as CallSceneMember;
const THEO = { character_id: 'theo', display_name: 'Theo Lark', role: 'guest', seat: 2 } as CallSceneMember;

function view(members: CallSceneMember[], available = true): CallSceneView {
  return { available, reason: available ? 'ready' : 'scene_needs_character_chat', max_guests: 2, members } as CallSceneView;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

let scene: CallSceneView = view([HOST, BEA]);
let posted: unknown[] = [];
let deleted: string[] = [];

function character(id: string, name: string, patch: Record<string, unknown> = {}) {
  return { id, display_name: name, enabled: true, status: 'active', ...patch };
}

beforeEach(() => {
  scene = view([HOST, BEA]);
  posted = [];
  deleted = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    const method = (init?.method ?? request?.method ?? 'GET').toUpperCase();
    if (path === SCENE_PATH) return json(scene);
    if (path === `${SCENE_PATH}/guests` && method === 'POST') {
      posted.push(JSON.parse(request ? await request.clone().text() : String(init?.body)));
      scene = view([HOST, BEA, THEO]);
      return json(scene);
    }
    if (path.startsWith(`${SCENE_PATH}/guests/`) && method === 'DELETE') {
      deleted.push(path.split('/').pop() ?? '');
      scene = view([HOST]);
      return json(scene);
    }
    return json(null);
  }));
  vi.spyOn(characterClient, 'refreshLiveCallRuntime').mockResolvedValue(null as never);
  vi.spyOn(characterClient, 'list').mockResolvedValue({
    characters: [
      character('mara', 'Mara Quinn'),
      character('bea', 'Bea Hart'),
      character('theo', 'Theo Lark'),
      character('old', 'Old Friend', { status: 'archived' }),
      character('off', 'Switched Off', { enabled: false }),
    ],
  } as never);
  callSceneStore.resetForTests();
  liveCallPresentationStore.resetForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  callSceneStore.resetForTests();
  liveCallPresentationStore.resetForTests();
});

describe('the call members', () => {
  it('lists the host and guests and lights up whoever is speaking', async () => {
    renderWithProviders(<LiveCallScene sessionId="s1" />);
    const members = await screen.findByRole('region', { name: 'On this call' });
    const items = within(members).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual(['Mara Quinn', 'Bea HartRemove']);
    // Only a guest can be removed; the host is the chat's own character.
    expect(within(items[0]).queryByRole('button')).toBeNull();
    expect(items.some((item) => item.getAttribute('aria-current'))).toBe(false);

    liveCallPresentationStore.update({ speaking: true, sceneSpeakerId: null });
    await waitFor(() => expect(items[0].getAttribute('aria-current')).toBe('true'));
    liveCallPresentationStore.update({ sceneSpeakerId: 'bea' });
    await waitFor(() => expect(items[1].getAttribute('aria-current')).toBe('true'));
    expect(items[0].getAttribute('aria-current')).toBeNull();
  });

  it('offers only active characters not already on the call, and adds the one chosen', async () => {
    renderWithProviders(<LiveCallScene sessionId="s1" />);
    const select = await screen.findByRole('combobox', { name: 'Character to add to the call' });
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual(['Theo Lark']);

    fireEvent.click(screen.getByRole('button', { name: 'Add to call' }));
    await screen.findByText('Theo Lark', { selector: 'span' });
    expect(posted).toEqual([{ character_id: 'theo' }]);
    // Two guests fill the call: nothing more can be added.
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('removes a guest', async () => {
    renderWithProviders(<LiveCallScene sessionId="s1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Remove Bea Hart from the call' }));

    await waitFor(() => expect(screen.queryByText('Bea Hart', { selector: 'span' })).toBeNull());
    expect(deleted).toEqual(['bea']);
  });

  it('shows nothing where a chat cannot have guests', async () => {
    scene = view([], false);
    const { container } = renderWithProviders(<LiveCallScene sessionId="s1" />);

    await waitFor(() => expect(callSceneStore.getState().loading).toBe(false));
    expect(container.querySelector('.live-call-scene')).toBeNull();
  });
});

describe("a guest's reply in the transcript", () => {
  it('names the guest the server recorded, and nobody for a reply without a scene', () => {
    expect(sceneSpeakerName({ speaker_character_id: 'bea', speaker_name: 'Bea Hart' })).toBe('Bea Hart');
    expect(sceneSpeakerName({ speaker_name: '  ' })).toBeNull();
    expect(sceneSpeakerName(null)).toBeNull();
    expect(sceneSpeakerName('Bea Hart')).toBeNull();
  });

  it('carries the speaker into the live transcript for assistant replies only', () => {
    const messages = liveChatMessagesFor([
      { id: 'm1', role: 'user', content: 'Were you there?', created_at: '2026-11-15T10:00:00Z', metadata: { speaker_name: 'X' } },
      { id: 'm2', role: 'assistant', content: 'I was.', created_at: '2026-11-15T10:00:02Z', metadata: { speaker_name: 'Bea Hart' } },
      { id: 'm3', role: 'assistant', content: 'So was I.', created_at: '2026-11-15T10:00:04Z', metadata: {} },
    ] as never, { rows: [] } as never);
    expect(messages.map((message) => [message.text, message.speaker])).toEqual([
      ['Were you there?', null],
      ['I was.', 'Bea Hart'],
      ['So was I.', null],
    ]);
  });

  it('offers "Let them talk" only with the talk setting on and a guest on the call, and starts on with each call', async () => {
    liveConversationStore.dispatch({ type: 'profile', profile: { scene_talk_enabled: false } as LiveConversationProfile });
    renderWithProviders(<LiveCallScene sessionId="s1" />);
    await screen.findByRole('region', { name: 'On this call' });
    expect(screen.queryByLabelText('Let them talk')).toBeNull();

    liveConversationStore.dispatch({ type: 'profile', profile: { scene_talk_enabled: true } as LiveConversationProfile });
    const toggle = await screen.findByLabelText('Let them talk');
    expect(toggle).toBeChecked();
    expect(toggle).toBeDisabled();  // only while a call runs
    liveCallPresentationStore.update({ captureActive: true });
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    await waitFor(() => expect(liveCallPresentationStore.getState().sceneTalkOn).toBe(false));

    // The call ends: the next one starts with them talking again.
    stopLiveVoice(document.createElement('div'), 'idle');
    expect(liveCallPresentationStore.getState().sceneTalkOn).toBe(true);
    liveConversationStore.reset();
  });
});
