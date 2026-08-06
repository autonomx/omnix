import { describe, expect, it } from 'vitest';

import {
  AdaptiveTtsBufferPolicy,
  adaptiveBufferWorkletMessage,
} from './live-tts-adaptive-buffer-controller';

describe('adaptive live TTS buffering', () => {
  it('starts with a 160 ms speech reserve at 24 kHz', () => {
    const policy = new AdaptiveTtsBufferPolicy();
    const snapshot = policy.snapshot();

    expect(snapshot).toMatchObject({
      startBufferMs: 160,
      rebufferMs: 520,
      stableTurns: 0,
      underrunTurns: 0,
    });
    expect(adaptiveBufferWorkletMessage(snapshot, 24_000)).toMatchObject({
      startBufferSamples: 3_840,
      minimumBufferedSpeechSamples: 3_840,
      rebufferSamples: 12_480,
    });
  });

  it('immediately restores a larger safety reserve after an underrun', () => {
    const policy = new AdaptiveTtsBufferPolicy();

    expect(policy.observeWorkletEvent('underrun')).toMatchObject({
      startBufferMs: 230,
      rebufferMs: 630,
    });
    expect(policy.observeWorkletEvent('drained')).toMatchObject({
      startBufferMs: 230,
      rebufferMs: 630,
      stableTurns: 0,
      underrunTurns: 1,
    });
  });

  it('only reduces the reserve after three complete stable turns', () => {
    const policy = new AdaptiveTtsBufferPolicy();

    policy.observeWorkletEvent('drained');
    policy.observeWorkletEvent('drained');
    expect(policy.snapshot().startBufferMs).toBe(160);

    expect(policy.observeWorkletEvent('drained')).toMatchObject({
      startBufferMs: 140,
      rebufferMs: 490,
      stableTurns: 0,
    });
  });
});
