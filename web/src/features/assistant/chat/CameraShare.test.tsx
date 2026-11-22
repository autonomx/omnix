import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { cameraShareState, resetCameraShareForTests, startCameraShare } from '../workspace/camera-share';
import { liveCallPresentationStore } from '../workspace/live-call-presentation-store';
import { resetLiveCallCameraForTests } from '../workspace/live-call-camera';
import { liveConversationStore } from '../workspace/live-conversation-store';
import { CameraSelfView, CameraShareButton } from './CameraShare';
import { LiveShowButton } from './LiveShowButton';

let stops: Array<ReturnType<typeof vi.fn>> = [];
let initialPresentation = liveCallPresentationStore.getState();

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  stops = [];
  initialPresentation = liveCallPresentationStore.getState();
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => {
        const track = { stop: vi.fn(), addEventListener: vi.fn() };
        stops.push(track.stop);
        return { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream;
      }),
    },
  });
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    if (path === '/api/chat/sessions/s1/live-call/camera') return json({ available: true, remote: false, reason: 'ready' });
    return json(null);
  }));
  resetCameraShareForTests();
  resetLiveCallCameraForTests();
  liveConversationStore.reset();
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
});

afterEach(() => {
  resetCameraShareForTests();
  resetLiveCallCameraForTests();
  liveConversationStore.reset();
  liveCallPresentationStore.update(initialPresentation);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'mediaDevices');
});

describe('CameraShareButton', () => {
  it('turns the camera share on and off from the composer', async () => {
    render(<CameraShareButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Share the camera' }));
    const stop = await screen.findByRole('button', { name: 'Stop sharing the camera' });

    expect(stop).toHaveAttribute('aria-pressed', 'true');
    expect(stop).toHaveTextContent('CameraSharing');
    fireEvent.click(stop);

    expect(stops[0]).toHaveBeenCalledTimes(1);
    expect(cameraShareState().phase).toBe('off');
    expect(screen.getByRole('button', { name: 'Share the camera' })).toHaveTextContent('CameraOff');
  });

  it('shows why the camera stopped, and the message can be dismissed', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => { throw new DOMException('no', 'NotAllowedError'); }) },
    });
    render(<CameraShareButton variant="call" />);

    fireEvent.click(screen.getByRole('button', { name: 'Share the camera' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Camera access was not allowed.');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss camera message' }));
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('CameraSelfView', () => {
  it('shows the person their own mirrored camera only while it is shared', async () => {
    const { container } = render(<CameraSelfView />);
    expect(container.innerHTML).toBe('');

    await act(async () => startCameraShare());

    const video = screen.getByLabelText('Your shared camera') as HTMLVideoElement;
    expect(video.srcObject).toBe(cameraShareState().stream);
    expect(video.muted).toBe(true);
    expect(screen.getByText('Camera on')).toBeInTheDocument();

    act(() => resetCameraShareForTests());
    expect(container.innerHTML).toBe('');
  });
});

describe('LiveShowButton while the camera is shared', () => {
  it('steps aside: the call already sees the camera', async () => {
    act(() => liveCallPresentationStore.update({ captureOwned: true, captureActive: true }));
    const { container } = render(<LiveShowButton />);
    await screen.findByRole('button', { name: 'Show the companion something with your camera' });

    await act(async () => startCameraShare());

    expect(container.innerHTML).toBe('');
  });
});
