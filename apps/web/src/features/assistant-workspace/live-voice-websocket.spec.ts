import { describe, expect, it } from 'vitest';
import {
  calculateRms,
  downsampleFloat32To16Khz,
  encodePcm16Base64,
  getDefaultStreamingSttWebSocketUrl,
} from './live-voice-websocket';

describe('live voice websocket helpers', () => {
  it('builds the local transcription websocket URL from the browser location', () => {
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'http:', hostname: 'localhost' })).toBe('ws://localhost:8000/ws/transcribe');
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'https:', hostname: 'omnix.local' })).toBe('wss://omnix.local:8000/ws/transcribe');
  });

  it('downsamples audio frames to 16khz deterministically', () => {
    const input = new Float32Array([0, 0.25, 0.5, 0.75, 1, 0.75]);
    const output = downsampleFloat32To16Khz(input, 48_000, 16_000);

    expect(Array.from(output)).toEqual([0, 0.75]);
  });

  it('encodes clipped pcm16 audio as base64 payloads for the STT websocket', () => {
    expect(encodePcm16Base64(new Float32Array([-2, 0, 2]))).toBe('AYAAAP9/');
  });

  it('calculates rms for voice activity detection', () => {
    expect(calculateRms(new Float32Array([0, 0, 0]))).toBe(0);
    expect(calculateRms(new Float32Array([1, -1]))).toBe(1);
  });
});
