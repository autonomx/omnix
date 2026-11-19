import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { liveCallPresentationStore } from '../workspace/live-call-presentation-store';
import { liveCallCameraState, noteLiveCallCameraRequest, resetLiveCallCameraForTests, takeLiveCallCameraFrame } from '../workspace/live-call-camera';
import { liveConversationStore } from '../workspace/live-conversation-store';
import { LiveShowButton } from './LiveShowButton';

let stops: Array<ReturnType<typeof vi.fn>> = [];
let getUserMedia: ReturnType<typeof vi.fn>;
let available = true;
let initialPresentation = liveCallPresentationStore.getState();

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  stops = [];
  available = true;
  initialPresentation = liveCallPresentationStore.getState();
  getUserMedia = vi.fn(async () => {
    const stop = vi.fn();
    stops.push(stop);
    return { getTracks: () => [{ stop }] } as unknown as MediaStream;
  });
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: () => undefined } as never);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,AAAA');
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 640 });
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 480 });
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    if (path === '/api/chat/sessions/s1/live-call/camera') {
      return json({ available, remote: false, reason: available ? 'ready' : 'vision_not_configured' });
    }
    return json(null);
  }));
  resetLiveCallCameraForTests();
  liveConversationStore.reset();
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
});

afterEach(() => {
  resetLiveCallCameraForTests();
  liveConversationStore.reset();
  liveCallPresentationStore.update(initialPresentation);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'mediaDevices');
  Reflect.deleteProperty(HTMLVideoElement.prototype, 'videoWidth');
  Reflect.deleteProperty(HTMLVideoElement.prototype, 'videoHeight');
});

async function renderDuringCall() {
  act(() => liveCallPresentationStore.update({ captureOwned: true, captureActive: true }));
  const view = render(<LiveShowButton />);
  await screen.findByRole('button', { name: 'Show the companion something with your camera' });
  return view;
}

describe('LiveShowButton', () => {
  it('is hidden outside a call and when the call cannot see', async () => {
    const { container, rerender } = render(<LiveShowButton />);
    expect(container.innerHTML).toBe('');

    available = false;
    act(() => liveCallPresentationStore.update({ captureOwned: true, captureActive: true }));
    rerender(<LiveShowButton />);
    await vi.waitFor(() => expect(liveCallCameraState().availabilitySessionId).toBe('s1'));
    expect(container.innerHTML).toBe('');
  });

  it('opens the camera with "Camera on" and takes one picture, stopping the camera', async () => {
    await renderDuringCall();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Show the companion something with your camera' }));
    });
    expect(screen.getByRole('status').textContent).toBe('Camera on');
    expect(screen.getByLabelText('Camera preview')).toBeTruthy();

    act(() => fireEvent.click(screen.getByRole('button', { name: 'Take the picture' })));

    expect(stops[0]).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText('Camera preview')).toBeNull();
    expect(screen.getByText('Picture ready: it goes with what you say next.')).toBeTruthy();
    expect(takeLiveCallCameraFrame()).toBe('data:image/jpeg;base64,AAAA');
  });

  it('closing the preview stops the camera', async () => {
    await renderDuringCall();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Show the companion something with your camera' }));
    });

    act(() => fireEvent.click(screen.getByRole('button', { name: 'Close camera' })));

    expect(stops[0]).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Camera on')).toBeNull();
  });

  it('a request from the call makes Show stand out but opens nothing', async () => {
    await renderDuringCall();

    act(() => noteLiveCallCameraRequest('the label on the jar'));

    const button = screen.getByRole('button', { name: 'Show the companion the label on the jar' });
    expect(button.className).toContain('requested');
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('the call ending hides Show', async () => {
    const { container } = await renderDuringCall();

    act(() => liveCallPresentationStore.update({ captureActive: false }));

    expect(container.innerHTML).toBe('');
  });
});
