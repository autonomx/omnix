import { describe, expect, it } from 'vitest';
import {
  createFetchSpeechServiceTransport,
  createSttServiceClient,
  createTtsServiceClient,
  type SpeechServiceTransportRequest,
} from './speech-services';

describe('speech service clients', () => {
  it('posts audio to the configured STT service', async () => {
    const requests: SpeechServiceTransportRequest[] = [];
    const client = createSttServiceClient({
      baseUrl: 'http://localhost:5201/',
      transport: async (request) => {
        requests.push(request);
        return { text: 'hello omnix', confidence: 0.91 };
      },
    });

    const response = await client.transcribeAudio({
      audio: new Uint8Array([1, 2, 3]),
      language: 'en',
      prompt: 'short command',
    });

    expect(response.text).toBe('hello omnix');
    expect(requests[0]).toMatchObject({ url: 'http://localhost:5201/transcribe', method: 'POST' });
    expect(requests[0]?.body).toBeInstanceOf(FormData);
  });

  it('posts synthesis requests to the configured TTS service', async () => {
    const requests: SpeechServiceTransportRequest[] = [];
    const client = createTtsServiceClient({
      baseUrl: 'http://localhost:5101',
      transport: async (request) => {
        requests.push(request);
        return { audioUrl: 'blob:voice', mimeType: 'audio/wav', durationSeconds: 1.5 };
      },
    });

    const response = await client.synthesizeSpeech({ text: 'Welcome back.', voice: 'narrator', format: 'wav' });

    expect(response.audioUrl).toBe('blob:voice');
    expect(requests[0]).toMatchObject({
      url: 'http://localhost:5101/synthesize',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    expect(requests[0]?.body).toBe(JSON.stringify({ text: 'Welcome back.', voice: 'narrator', format: 'wav' }));
  });

  it('converts failed fetch responses into service errors', async () => {
    const transport = createFetchSpeechServiceTransport(async () => new Response('offline', { status: 503 }) as Response);

    await expect(
      transport({
        url: 'http://localhost:5101/synthesize',
        method: 'POST',
        body: JSON.stringify({ text: 'test' }),
      }),
    ).rejects.toThrow('Speech service request failed with status 503');
  });
});
