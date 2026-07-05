import { waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const player = vi.hoisted(() => {
  let activeButton: HTMLButtonElement | null = null;
  return {
    start: vi.fn(async (_root: ParentNode, button: HTMLButtonElement) => {
      activeButton = button;
      queueMicrotask(() => { activeButton = null; });
    }),
    stop: vi.fn(() => { activeButton = null; }),
    isActive: vi.fn((button: HTMLButtonElement) => activeButton === button),
    keepActive(button: HTMLButtonElement) {
      activeButton = button;
    },
  };
});

vi.mock('./assistant-pcm-stream-websocket-player', () => ({
  startAssistantPcmStream: player.start,
  stopAssistantPcmStream: player.stop,
  isAssistantPcmStreamActive: player.isActive,
}));

import {
  initializeLiveVoiceUnifiedAudioController,
  shouldUseUnifiedLiveVoiceAudio,
} from './live-voice-unified-audio-controller';

let cleanup: (() => void) | null = null;

function renderLiveVoice(active = true, autoSpeak = true): void {
  document.body.innerHTML = `
    <section class="assistant-live-card" data-live-voice-status="${active ? 'connected' : 'idle'}">
      <button type="button">${active ? 'End Call' : 'Start Call'}</button>
      <div class="assistant-voice-orb" data-voice-mode="${active ? 'listening' : 'idle'}"></div>
      <label class="assistant-voice-toggle"><input type="checkbox" ${autoSpeak ? 'checked' : ''}> Auto-speak</label>
    </section>
    <div class="assistant-inline-status"></div>`;
}

function chatStreamResponse(): Response {
  const events = [
    { type: 'user_message', message: { id: 'u1' } },
    { type: 'text_chunk', text: 'Hello there. This response is long enough to become a spoken phrase.' },
    { type: 'session', session: { id: 's1', messages: [{ id: 'a1', role: 'assistant' }] } },
    { type: 'done' },
  ];
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

beforeEach(() => {
  renderLiveVoice();
  window.localStorage.clear();
  window.localStorage.setItem('omnix.chatbot.assistantSettings', JSON.stringify({ voiceId: 'Jinx' }));
  vi.stubGlobal('fetch', vi.fn(async () => chatStreamResponse()));
  player.start.mockClear();
  player.stop.mockClear();
  player.isActive.mockClear();
  cleanup = initializeLiveVoiceUnifiedAudioController();
});

afterEach(() => {
  cleanup?.();
  cleanup = null;
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('live voice unified audio controller', () => {
  it('routes live text chunks through the shared PCM player and hides them from the legacy scheduler', async () => {
    const response = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    const applicationEvents = await response.text();

    expect(applicationEvents).not.toContain('text_chunk');
    expect(applicationEvents).toContain('user_message');
    expect(applicationEvents).toContain('session');
    expect(applicationEvents).toContain('done');

    await waitFor(() => expect(player.start).toHaveBeenCalledTimes(1));
    expect(player.start).toHaveBeenCalledWith(
      document,
      expect.any(HTMLButtonElement),
      'Hello there. This response is long enough to become a spoken phrase.',
    );
    expect(document.querySelector<HTMLSelectElement>('select[data-omnix-live-voice-bridge]')?.value).toBe('Jinx');
    await waitFor(() => expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening'));
  });

  it('leaves non-live and auto-speak-disabled chat streams untouched', async () => {
    cleanup?.();
    renderLiveVoice(false, true);
    cleanup = initializeLiveVoiceUnifiedAudioController();

    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(false);
    const inactiveResponse = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    expect(await inactiveResponse.text()).toContain('text_chunk');

    cleanup?.();
    renderLiveVoice(true, false);
    cleanup = initializeLiveVoiceUnifiedAudioController();
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(false);
    const disabledResponse = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    expect(await disabledResponse.text()).toContain('text_chunk');
    expect(player.start).not.toHaveBeenCalled();
  });

  it('uses the shared stop path for live voice interruption', async () => {
    player.start.mockImplementationOnce(async (_root: ParentNode, button: HTMLButtonElement) => {
      player.keepActive(button);
    });

    const response = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    await response.text();
    await waitFor(() => expect(player.start).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-interrupt'));

    expect(player.stop).toHaveBeenCalled();
    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');
  });
});
