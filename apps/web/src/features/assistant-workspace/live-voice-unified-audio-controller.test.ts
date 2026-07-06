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
let streamEvents: Array<Record<string, unknown>> | null = null;

function renderLiveVoice(active = true, autoSpeak = true): void {
  document.body.innerHTML = `
    <section class="assistant-live-card" data-live-voice-status="${active ? 'connected' : 'idle'}">
      <button type="button">${active ? 'End Call' : 'Start Call'}</button>
      <div class="assistant-voice-orb" data-voice-mode="${active ? 'listening' : 'idle'}"></div>
      <label class="assistant-voice-toggle"><input type="checkbox" ${autoSpeak ? 'checked' : ''}> Auto-speak</label>
    </section>
    <div class="assistant-inline-status"></div>`;
}

function chatStreamResponse(events: Array<Record<string, unknown>> = [
  { type: 'user_message', message: { id: 'u1' } },
  { type: 'text_chunk', text: 'Hello there. This first phrase is ready for speech.' },
  { type: 'text_chunk', text: 'The second phrase should enter the same continuous queue.' },
  { type: 'session', session: { id: 's1', messages: [{ id: 'a1', role: 'assistant' }] } },
  { type: 'done' },
]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

beforeEach(() => {
  renderLiveVoice();
  streamEvents = null;
  window.localStorage.clear();
  window.localStorage.setItem('omnix.chatbot.assistantSettings', JSON.stringify({ voiceId: 'Jinx' }));
  vi.stubGlobal('fetch', vi.fn(async () => chatStreamResponse(streamEvents ?? undefined)));
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
  it('records installation and uses one persistent PCM session for every phrase', async () => {
    expect(mocks.reporter.record).toHaveBeenCalledWith(
      'controller_installed',
      expect.objectContaining({ fetch_wrapped: true }),
      'controller',
    );
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

  it('skips non-speech-only trailing chunks without stopping the turn', async () => {
    streamEvents = [
      { type: 'user_message', message: { id: 'u1' } },
      { type: 'text_chunk', text: 'Here is a complete spoken answer for the live call.' },
      { type: 'text_chunk', text: '☀️' },
      { type: 'text_chunk', text: '✨' },
      { type: 'session', session: { id: 's1', messages: [{ id: 'a1', role: 'assistant' }] } },
      { type: 'done' },
    ];

    const response = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    await response.text();

    await waitFor(() => expect(mocks.session.enqueuePhrase).toHaveBeenCalledTimes(1));
    expect(mocks.session.enqueuePhrase).toHaveBeenCalledWith(
      'Here is a complete spoken answer for the live call.',
      0,
    );
    expect(mocks.reporter.record).toHaveBeenCalledWith(
      'phrase_skipped',
      expect.objectContaining({ reason: 'non-speech-only', text: '☀️ ✨' }),
      'controller',
    );
    await waitFor(() => expect(mocks.session.finish).toHaveBeenCalledTimes(1));
    expect(mocks.session.stop).not.toHaveBeenCalled();
    await waitFor(() => expect(mocks.reporter.close).toHaveBeenCalledWith(
      'turn_finished',
      expect.objectContaining({ phrases: 1, text_chunks: 3 }),
    ));
  });

  it('uses the live streaming endpoint as the activation signal and respects Auto-speak', () => {
    renderLiveVoice(false, true);
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(true);

    renderLiveVoice(true, false);
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(false);
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages', { method: 'POST' })).toBe(false);
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'GET' })).toBe(false);
  });

  it('stops the persistent live session on interruption', async () => {
    let finishResolve: () => void = () => undefined;
    mocks.session.finish.mockImplementationOnce(() => new Promise<undefined>((resolve) => {
      finishResolve = () => resolve(undefined);
    }));

    const response = await window.fetch('/api/chat/sessions/s1/messages/stream', { method: 'POST' });
    await response.text();
    await waitFor(() => expect(mocks.session.finish).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-interrupt'));

    await waitFor(() => expect(mocks.session.stop).toHaveBeenCalledWith('voice-interrupt'));
    expect(mocks.stopButtonStream).toHaveBeenCalled();
    await waitFor(() => expect(mocks.reporter.close).toHaveBeenCalledWith(
      'turn_stopped',
      { reason: 'voice-interrupt' },
    ));
    expect(document.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode).toBe('listening');
    finishResolve();
  });
});
