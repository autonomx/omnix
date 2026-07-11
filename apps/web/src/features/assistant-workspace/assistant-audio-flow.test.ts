import { afterEach, describe, expect, it } from 'vitest';
import { mergePcmChunks } from './assistant-buffered-tts-player';
import { isChatAudioButton, isStreamAudioButton } from './chat-message-audio-controller-v2';
import {
  appendStreamText,
  filterLiveVoiceTextChunks,
  shouldUseSmoothLiveVoiceAudio,
} from './live-voice-smooth-audio-controller';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('assistant audio flow', () => {
  it('merges PCM chunks without dropping samples', () => {
    const merged = mergePcmChunks([
      new Int16Array([1, 2]),
      new Int16Array(),
      new Int16Array([3, 4, 5]),
    ]);

    expect(Array.from(merged)).toEqual([1, 2, 3, 4, 5]);
  });

  it('distinguishes the low-latency stream button from normal play controls', () => {
    document.body.innerHTML = `
      <article class="assistant-chat-message assistant">
        <div class="assistant-chat-bubble"><p>Hello there.</p></div>
        <div class="assistant-message-actions">
          <button data-omnix-stream-audio="true" aria-label="Stream response audio">≋</button>
          <button aria-label="Play response audio">▶</button>
          <button>Play audio</button>
        </div>
      </article>
    `;
    const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('button'));

    expect(isStreamAudioButton(buttons[0])).toBe(true);
    expect(isChatAudioButton(buttons[0])).toBe(true);
    expect(isStreamAudioButton(buttons[1])).toBe(false);
    expect(isChatAudioButton(buttons[1])).toBe(true);
    expect(isChatAudioButton(buttons[2])).toBe(true);
  });

  it('uses smooth buffered playback only for an active auto-speak live call', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-status="connected">
        <label class="assistant-voice-toggle"><input type="checkbox" checked /></label>
        <button>End Call</button>
      </section>
    `;

    expect(shouldUseSmoothLiveVoiceAudio('/api/chat/sessions/session-1/messages/stream', {
      method: 'POST',
    })).toBe(true);
    expect(shouldUseSmoothLiveVoiceAudio('/api/chat/sessions/session-1/messages/stream', {
      method: 'GET',
    })).toBe(false);

    const toggle = document.querySelector<HTMLInputElement>('.assistant-voice-toggle input');
    if (toggle) toggle.checked = false;
    expect(shouldUseSmoothLiveVoiceAudio('/api/chat/sessions/session-1/messages/stream', {
      method: 'POST',
    })).toBe(false);
  });

  it('preserves streamed punctuation while assembling one smooth utterance', () => {
    let text = '';
    text = appendStreamText(text, 'Hello');
    text = appendStreamText(text, ',');
    text = appendStreamText(text, ' Maya');
    text = appendStreamText(text, '!');

    expect(text).toBe('Hello, Maya!');
  });

  it('removes legacy text chunks while preserving session events for the UI', async () => {
    const encoder = new TextEncoder();
    const source = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(
          'data: {"type":"text_chunk","text":"Hello"}\n\n'
          + 'data: {"type":"session","session":{"id":"session-1"}}\n\n',
        ));
        controller.close();
      },
    });
    const reader = filterLiveVoiceTextChunks(source).getReader();
    const decoder = new TextDecoder();
    let output = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      output += decoder.decode(value, { stream: true });
    }
    output += decoder.decode();

    expect(output).not.toContain('text_chunk');
    expect(output).toContain('"type":"session"');
  });
});
