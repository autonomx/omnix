import { afterEach, describe, expect, it, vi } from 'vitest';
import { playPreview } from './PortraitAvatarSetup';

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  currentTime = 0;
  destination = {};
  closed = false;
  readonly source = { buffer: null as unknown, connect: vi.fn(), start: vi.fn(), stop: vi.fn(), onended: null as null | (() => void) };
  createBuffer(_channels: number, length: number, rate: number) {
    const data = new Float32Array(length);
    return { length, sampleRate: rate, getChannelData: () => data };
  }
  createBufferSource() { return this.source; }
  close() { this.closed = true; return Promise.resolve(); }
  constructor() { FakeAudioContext.instances.push(this); }
}

afterEach(() => vi.unstubAllGlobals());

describe('the portrait preview player', () => {
  it('plays the audio and draws the frame for its clock, then stops and releases everything', async () => {
    vi.stubGlobal('AudioContext', FakeAudioContext);
    const closed: number[] = [];
    vi.stubGlobal('createImageBitmap', async (blob: Blob) => ({ id: blob.size, close: () => closed.push(blob.size) }));
    const frames: (() => void)[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: () => void) => frames.push(callback));
    vi.stubGlobal('cancelAnimationFrame', () => undefined);
    const drawn: number[] = [];
    const canvas = { width: 512, height: 512, getContext: () => ({ drawImage: (image: { id: number }) => drawn.push(image.id) }) };
    const pcm = btoa(String.fromCharCode(0, 64, 0, 192));
    const jpegs = [btoa('a'), btoa('bb'), btoa('ccc')];
    const ended = vi.fn();
    const stop = playPreview({ ok: true, code: '', message: '', sample_rate: 24_000, audio: pcm, fps: 25, frames: jpegs },
      canvas as unknown as HTMLCanvasElement, ended);
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const context = FakeAudioContext.instances[0];
    expect(context.source.start).toHaveBeenCalledWith(0.1);
    context.currentTime = 0.1 + 0.05; // the second frame (40-80 ms)
    frames.shift()?.();
    expect(drawn).toEqual([2]);
    context.source.onended?.();
    expect(ended).toHaveBeenCalled();
    expect(context.closed).toBe(true);
    expect(closed.sort()).toEqual([1, 2, 3]);
    stop();
  });
});
