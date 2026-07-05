import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  initializeChatMessageStreamAudioController,
  injectStreamAudioButtons,
} from './chat-message-stream-audio-controller';

type SourceListener = () => void;

class FakeAudioParam {
  setValueAtTime = vi.fn();
  linearRampToValueAtTime = vi.fn();
}

class FakeGainNode {
  gain = new FakeAudioParam();
  connect = vi.fn();
  disconnect = vi.fn();
}

class FakeAudioBufferSource {
  buffer: AudioBuffer | null = null;
  private endedListener: SourceListener | null = null;
  connect = vi.fn();
  disconnect = vi.fn();
  stop = vi.fn();
  start = vi.fn(() => queueMicrotask(() => this.endedListener?.()));

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (type !== 'ended') return;
    this.endedListener = typeof listener === 'function'
      ? () => listener(new Event('ended'))
      : () => listener.handleEvent(new Event('ended'));
  }
}

class FakeAudioContext {
  static sources: FakeAudioBufferSource[] = [];
  static gains: FakeGainNode[] = [];
  state: AudioContextState = 'running';
  currentTime = 0;
  destination = {} as AudioDestinationNode;
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);

  createBuffer(_channels: number, length: number, sampleRate: number): AudioBuffer {
    return {
      duration: length / sampleRate,
      getChannelData: () => new Float32Array(length),
    } as unknown as AudioBuffer;
  }

  createBufferSource(): AudioBufferSourceNode {
    const source = new FakeAudioBufferSource();
    FakeAudioContext.sources.push(source);
    return source as unknown as AudioBufferSourceNode;
  }

  createGain(): GainNode {
    const gain = new FakeGainNode();
    FakeAudioContext.gains.push(gain);
    return gain as unknown as GainNode;
  }
}

function renderAssistantMessage(text = 'Stream this assistant reply.'): void {
  document.body.innerHTML = `
    <select aria-label="Cloned voice"><option value="ari-clone" selected>Ari Clone</option></select>
    <article class="assistant-chat-message assistant">
      <div class="assistant-chat-bubble">
        <p>${text}</p>
        <div class="assistant-message-actions" aria-label="Assistant message actions">
          <button type="button" aria-label="Play response audio">▶</button>
          <button type="button" aria-label="More response actions">⋮</button>
        </div>
      </div>
    </article>
    <div class="assistant-inline-status" aria-live="polite"></div>
  `;
}

function pcmChunkBase64(sampleCount: number): string {
  return window.btoa(String.fromCharCode(...new Uint8Array(sampleCount * 2)));
}

afterEach(() => {
  document.body.innerHTML = '';
  FakeAudioContext.sources = [];
  FakeAudioContext.gains = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('chat message streaming audio controller', () => {
  it('streams an assistant message through the live TTS SSE contract', async () => {
    renderAssistantMessage();
    vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
    vi.stubGlobal('ReadableStream', ReadableStream);
    const fetchMock = vi.fn().mockResolvedValue(new Response([
      'data: {"type":"chunk","audio_b64":"AAAAAA==","sample_rate":24000}',
      '',
      'data: {"type":"done"}',
      '',
    ].join('\n'), { status: 200, headers: { 'Content-Type': 'text/event-stream' } }));
    vi.stubGlobal('fetch', fetchMock);

    const cleanup = initializeChatMessageStreamAudioController();
    const streamButton = document.querySelector<HTMLButtonElement>('button[aria-label="Stream response audio"]');
    expect(streamButton).not.toBeNull();
    expect(streamButton?.nextElementSibling).toHaveAttribute('aria-label', 'More response actions');

    fireEvent.click(streamButton as HTMLButtonElement);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/tts/stream/server-sent-events');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({
      text: 'Stream this assistant reply.',
      speaker: 'ari-clone',
      non_streaming_mode: false,
      parity_mode: true,
    });

    await waitFor(() => expect(FakeAudioContext.sources[0]?.start).toHaveBeenCalled());
    expect(FakeAudioContext.gains[0]?.gain.linearRampToValueAtTime).toHaveBeenCalled();
    await waitFor(() => expect(document.body).toHaveTextContent('Streaming response audio finished.'));
    expect(document.querySelector('button[aria-label="Stream response audio"]')).not.toBeNull();
    cleanup();
  });

  it('buffers startup and crossfades adjacent PCM chunks', async () => {
    renderAssistantMessage();
    vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
    vi.stubGlobal('ReadableStream', ReadableStream);
    const chunk = pcmChunkBase64(2_400);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response([
      `data: {"type":"chunk","audio_b64":"${chunk}","sample_rate":24000}`,
      '',
      `data: {"type":"chunk","audio_b64":"${chunk}","sample_rate":24000}`,
      '',
      'data: {"type":"done"}',
      '',
    ].join('\n'), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })));

    const cleanup = initializeChatMessageStreamAudioController();
    fireEvent.click(document.querySelector('button[aria-label="Stream response audio"]') as HTMLButtonElement);

    await waitFor(() => expect(FakeAudioContext.sources).toHaveLength(2));
    const firstStart = FakeAudioContext.sources[0].start.mock.calls[0][0] as number;
    const secondStart = FakeAudioContext.sources[1].start.mock.calls[0][0] as number;
    const firstGainCalls = FakeAudioContext.gains[0].gain.linearRampToValueAtTime.mock.calls;
    const firstFadeOutAt = firstGainCalls[firstGainCalls.length - 1][1] as number;
    const secondFadeIn = FakeAudioContext.gains[1].gain.linearRampToValueAtTime.mock.calls[0] as [number, number];
    expect(firstStart).toBeCloseTo(0.18, 4);
    expect(secondStart).toBeCloseTo(0.272, 4);
    expect(firstFadeOutAt).toBeCloseTo(0.28, 4);
    expect(secondFadeIn[0]).toBe(1);
    expect(secondFadeIn[1]).toBeCloseTo(0.28, 4);
    cleanup();
  });

  it('adds the stream button to assistant messages mounted later', async () => {
    document.body.innerHTML = '<main id="chat-root"><div class="assistant-inline-status"></div></main>';
    const chatRoot = document.getElementById('chat-root') as HTMLElement;
    const cleanup = initializeChatMessageStreamAudioController(chatRoot);

    const message = document.createElement('article');
    message.className = 'assistant-chat-message assistant';
    message.innerHTML = '<div class="assistant-chat-bubble"><p>Later reply.</p><div class="assistant-message-actions"><button aria-label="More response actions">⋮</button></div></div>';
    chatRoot.appendChild(message);

    await waitFor(() => expect(chatRoot.querySelector('button[aria-label="Stream response audio"]')).not.toBeNull());
    cleanup();
  });

  it('does not duplicate an existing stream button', () => {
    renderAssistantMessage();
    injectStreamAudioButtons();
    injectStreamAudioButtons();
    expect(document.querySelectorAll('button[aria-label="Stream response audio"]')).toHaveLength(1);
  });
});
