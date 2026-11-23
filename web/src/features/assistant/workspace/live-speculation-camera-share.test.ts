import { afterEach, describe, expect, it, vi } from 'vitest';

import { pipelineFetch } from '../../../api/fetchPipeline';
import { LIVE_STT_SPECULATION_CANDIDATE_EVENT, LIVE_STT_SPECULATION_FINAL_EVENT } from '../../../events/bus';

const camera = vi.hoisted(() => ({ shared: false }));
vi.mock('./camera-share', () => ({ cameraShared: () => camera.shared }));

const { initializeLiveSpeculationController } = await import('./live-speculation-controller');

function speculationBodies(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([input]) => String(input).includes('/api/live/speculation/sessions/'))
    .map(([, init]) => JSON.parse(String((init as RequestInit | undefined)?.body ?? '{}')) as Record<string, unknown>);
}

describe('live speculation with a shared camera', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    camera.shared = false;
  });

  it('tells the gateway the camera is shared, so the early reply takes its description', async () => {
    const fetchMock = vi.fn(async () => new Response('', { status: 409 }));
    vi.stubGlobal('fetch', fetchMock);
    const cleanup = initializeLiveSpeculationController();
    const candidate = (segmentId: string) => window.dispatchEvent(new CustomEvent(LIVE_STT_SPECULATION_CANDIDATE_EVENT, {
      detail: { chatSessionId: 'chat:one', segmentId, sourceSequence: 1, text: 'can you see me now', probability: 0.95 },
    }));
    try {
      camera.shared = true;
      candidate('segment-shared');
      await vi.waitFor(() => expect(speculationBodies(fetchMock)).toHaveLength(1));
      camera.shared = false;
      candidate('segment-unshared');
      await vi.waitFor(() => expect(speculationBodies(fetchMock)).toHaveLength(2));

      const [shared, unshared] = speculationBodies(fetchMock);
      expect(shared).toMatchObject({ segment_id: 'segment-shared', camera_shared: true });
      expect(unshared).toMatchObject({ segment_id: 'segment-unshared' });
      expect(unshared).not.toHaveProperty('camera_shared');
    } finally {
      cleanup();
    }
  });

  it.each([
    { looking: true, reused: false },
    { looking: false, reused: true },
  ])('reuses an early reply only when it saw the camera (looking: $looking)', async ({ looking, reused }) => {
    const segmentId = `segment-looking-${String(looking)}`;
    const sse = [
      { type: 'speculation_started', generation_id: 'gen-1', provider_id: 'p', model_id: 'm' },
      { type: 'camera', generation_id: 'gen-1', looking },
      { type: 'text_chunk', generation_id: 'gen-1', text: 'I can see you.' },
      { type: 'done', generation_id: 'gen-1' },
    ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/live/speculation/sessions/') && url.endsWith('/stream')) {
        return new Response(sse, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
      }
      return new Response('normal turn', { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const cleanup = initializeLiveSpeculationController();
    const detail = { chatSessionId: 'chat:one', segmentId, sourceSequence: 1, text: 'can you see me now' };
    const chatStreamCalls = () => fetchMock.mock.calls.filter(([input]) => String(input).includes('/messages/stream'));
    try {
      camera.shared = true;
      window.dispatchEvent(new CustomEvent(LIVE_STT_SPECULATION_CANDIDATE_EVENT, { detail: { ...detail, probability: 0.95 } }));
      await vi.waitFor(() => expect(speculationBodies(fetchMock)).toHaveLength(1));
      window.dispatchEvent(new CustomEvent(LIVE_STT_SPECULATION_FINAL_EVENT, { detail }));

      await pipelineFetch('/api/chat/sessions/chat%3Aone/messages/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'can you see me now', camera_shared: true }),
      });

      // Written while the picture was still being described: the normal turn answers, with the picture.
      expect(chatStreamCalls()).toHaveLength(reused ? 0 : 1);
    } finally {
      cleanup();
    }
  });
});
