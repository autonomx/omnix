import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  closeLowLatencyVoiceCuePlayer,
  playLowLatencyVoiceCue,
  stopLowLatencyVoiceCue,
} from './live-voice-cue-player';

class FakeSource extends EventTarget {
  buffer: AudioBuffer | null = null;
  connect = vi.fn();
  disconnect = vi.fn();
  start = vi.fn();
  stop = vi.fn(() => this.dispatchEvent(new Event('ended')));

  finish(): void {
    this.dispatchEvent(new Event('ended'));
  }
}

class FakeAudioContext {
  static sources: FakeSource[] = [];
  state: AudioContextState = 'running';
  sampleRate = 24_000;
  destination = {} as AudioDestinationNode;
  resume = vi.fn(async () => undefined);
  close = vi.fn(async () => {
    this.state = 'closed';
  });
  createBuffer = vi.fn((_channels: number, length: number, sampleRate: number) => ({
    length,
    sampleRate,
    copyToChannel: vi.fn(),
  } as unknown as AudioBuffer));
  createBufferSource = vi.fn(() => {
    const source = new FakeSource();
    FakeAudioContext.sources.push(source);
    return source as unknown as AudioBufferSourceNode;
  });
  createGain = vi.fn(() => ({
    gain: { value: 1 },
    connect: vi.fn(),
  } as unknown as GainNode));
}

beforeEach(() => {
  FakeAudioContext.sources = [];
  vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
});

afterEach(async () => {
  await closeLowLatencyVoiceCuePlayer();
  vi.unstubAllGlobals();
});

describe('low-latency cue player', () => {
  it('publishes cue lifecycle without canonical speech progress', async () => {
    const events: Array<Record<string, unknown>> = [];
    const listener = ((event: CustomEvent<Record<string, unknown>>) => events.push(event.detail)) as EventListener;
    window.addEventListener('omnix:live-voice-cue-segment', listener);

    const played = playLowLatencyVoiceCue('mhm', 'mhm-v1');
    await vi.waitFor(() => expect(FakeAudioContext.sources).toHaveLength(1));
    FakeAudioContext.sources[0].finish();
    await expect(played).resolves.toBe(true);

    expect(events.map((event) => event.type)).toEqual(['segment_started', 'segment_completed']);
    expect(events.every((event) => event.segment_kind === 'cue')).toBe(true);
    expect(events.every((event) => event.semantic_speech_samples === 0)).toBe(true);
    window.removeEventListener('omnix:live-voice-cue-segment', listener);
  });

  it('reports interruption exactly once', async () => {
    const events: Array<Record<string, unknown>> = [];
    window.addEventListener('omnix:live-voice-cue-segment', ((event: CustomEvent<Record<string, unknown>>) => {
      events.push(event.detail);
    }) as EventListener);

    void playLowLatencyVoiceCue('inhale', 'inhale-v1');
    await vi.waitFor(() => expect(FakeAudioContext.sources).toHaveLength(1));
    stopLowLatencyVoiceCue('test_interrupt');

    expect(events.map((event) => event.type)).toEqual(['segment_started', 'segment_interrupted']);
    expect(events.at(-1)?.reason).toBe('test_interrupt');
  });
});
