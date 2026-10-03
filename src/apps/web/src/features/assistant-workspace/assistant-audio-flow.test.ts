/* eslint-disable no-restricted-syntax -- baseline WP-9.x */
import { afterEach, describe, expect, it } from 'vitest';
import { mergePcmChunks } from './assistant-buffered-tts-player';
import { isChatAudioButton, isStreamAudioButton } from './chat-message-audio-controller-v2';

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
});
