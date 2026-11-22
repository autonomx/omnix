import { afterEach, describe, expect, it, vi } from 'vitest';

import { LIVE_STT_SPECULATION_CANDIDATE_EVENT } from '../../../events/bus';

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
});
