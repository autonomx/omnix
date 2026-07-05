import { waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const session = {
    enqueuePhrase: vi.fn(async () => undefined),
    finish: vi.fn(async () => undefined),
    stop: vi.fn(async () => undefined),
    isClosed: vi.fn(() => false),
  };
  const reporter = {
    traceId: 'live-call:s1:test-trace',
    record: vi.fn(),
    flush: vi.fn(async () => undefined),
    close: vi.fn(async () => undefined),
  };
  return {
    session,
    reporter,
    createSession: vi.fn(async () => session),
    createReporter: vi.fn(() => reporter),
    createTraceId: vi.fn(() => 'live-call:s1:test-trace'),
    stopButtonStream: vi.fn(),
  };
});

vi.mock('./assistant-pcm-stream-websocket-player', () => ({
  stopAssistantPcmStream: mocks.stopButtonStream,
}));

vi.mock('./live-call-diagnostics-client', () => ({
  createLiveCallDiagnosticsReporter: mocks.createReporter,
  createLiveCallTraceId: mocks.createTraceId,
}));

vi.mock('./live-voice-pcm-session', () => ({
  createLiveVoicePcmSession: mocks.createSession,
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
    { type: 'text_chunk', text: 'Hello there. This first phrase is ready for speech.' },
    { type: 'text_chunk', text: 'The second phrase should enter the same continuous queue.' },
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
  mocks.session.enqueuePhrase.mockReset().mockResolvedValue(undefined);
  mocks.session.finish.mockReset().mockResolvedValue(undefined);
  mocks.session.stop.mockReset().mockResolvedValue(undefined);
  mocks.session.isClosed.mockReset().mockReturnValue(false);
  mocks.reporter.record.mockReset();
  mocks.reporter.flush.mockReset().mockResolvedValue(undefined);
  mocks.reporter.close.mockReset().mockResolvedValue(undefined);
  mocks.createSession.mockReset().mockResolvedValue(mocks.session);
  mocks.createReporter.mockReset().mockReturnValue(mocks.reporter);
  mocks.createTraceId.mockReset().mockReturnValue('live-call:s1:test-trace');
  mocks.stopButtonStream.mockReset();
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
  it('uses one persistent PCM session for every phrase in the live turn', async () => {
    const response = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    const applicationEvents = await response.text();

    expect(applicationEvents).not.toContain('text_chunk');
    expect(applicationEvents).toContain('user_message');
    expect(applicationEvents).toContain('session');
    expect(applicationEvents).toContain('done');

    await waitFor(() => expect(mocks.createSession).toHaveBeenCalledTimes(1));
    expect(mocks.createSession).toHaveBeenCalledWith(
      'live-call:s1:test-trace',
      'Jinx',
      mocks.reporter,
    );
    await waitFor(() => expect(mocks.session.enqueuePhrase).toHaveBeenCalledTimes(2));
    expect(mocks.session.enqueuePhrase).toHaveBeenNthCalledWith(
      1,
      'Hello there. This first phrase is ready for speech.',
      0,
    );
    expect(mocks.session.enqueuePhrase).toHaveBeenNthCalledWith(
      2,
      'The second phrase should enter the same continuous queue.',
      1,
    );
    await waitFor(() => expect(mocks.session.finish).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.reporter.close).toHaveBeenCalledWith(
      'turn_finished',
      expect.objectContaining({ phrases: 2, text_chunks: 2 }),
    ));
    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');
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
    expect(mocks.createSession).not.toHaveBeenCalled();
  });

  it('stops the persistent live session on interruption', async () => {
    let resolveFinish: (() => void) | null = null;
    mocks.session.finish.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveFinish = resolve;
    }));

    const response = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    await response.text();
    await waitFor(() => expect(mocks.session.finish).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-interrupt'));

    await waitFor(() => expect(mocks.session.stop).toHaveBeenCalledWith('live-call-stop'));
    expect(mocks.stopButtonStream).toHaveBeenCalled();
    await waitFor(() => expect(mocks.reporter.close).toHaveBeenCalledWith(
      'turn_stopped',
      { reason: 'live-call-stop' },
    ));
    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');
    resolveFinish?.();
  });
});
