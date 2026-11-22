import { useSyncExternalStore } from 'react';

import { unwrap } from '../../../api/http';
import { api } from '../api/gateway';

/**
 * The call's front camera, for one picture at a time (live companion roadmap 4.1). Only the person's press opens
 * it: the first press of Show starts the camera and shows a preview, the second takes one frame and stops the
 * camera at once. The frame waits for the person's next spoken turn and goes with it, once; closing the preview,
 * discarding the picture or ending the call drops it. The server keeps only a description, never the image.
 */
export type LiveCallCameraPhase = 'off' | 'opening' | 'preview' | 'attached' | 'error';

export type LiveCallCameraState = {
  phase: LiveCallCameraPhase;
  /** The open camera's stream, while the preview shows. */
  stream: MediaStream | null;
  /** What the call asked to see (companion 4.3); Show is shown prominently until the person answers. */
  requested: string | null;
  /** Whether this chat's call may offer Show: vision configured, and local or remote with consent. */
  available: boolean;
  /** The chat that availability was read for. */
  availabilitySessionId: string | null;
  error: string | null;
};

/** The frame's longest side, in pixels, and its JPEG quality. */
export const LIVE_CALL_CAMERA_LONGEST_SIDE = 1024;
export const LIVE_CALL_CAMERA_JPEG_QUALITY = 0.85;

function initialState(): LiveCallCameraState {
  return { phase: 'off', stream: null, requested: null, available: false, availabilitySessionId: null, error: null };
}

let state = initialState();
// The picture is kept out of the rendered state: nothing but the next turn reads it.
let frame: string | null = null;
// A camera that opens after its preview was closed is stopped as soon as it arrives.
let openToken = 0;
let availabilityToken = 0;
const listeners = new Set<() => void>();

function setState(change: Partial<LiveCallCameraState>): void {
  state = { ...state, ...change };
  listeners.forEach((listener) => listener());
}

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

export function liveCallCameraState(): LiveCallCameraState {
  return state;
}

export function useLiveCallCamera(): LiveCallCameraState {
  return useSyncExternalStore(subscribe, liveCallCameraState, liveCallCameraState);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The first press of Show: opens the front camera, video only, and shows the preview. */
export async function openLiveCallCamera(): Promise<void> {
  if (state.phase === 'opening' || state.phase === 'preview') return;
  frame = null;
  const token = ++openToken;
  setState({ phase: 'opening', error: null });
  let stream: MediaStream;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser has no camera access.');
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
  } catch (error) {
    if (token !== openToken) return;
    const denied = error instanceof DOMException && error.name === 'NotAllowedError';
    setState({ phase: 'error', stream: null, error: denied ? 'Camera access was not allowed.' : 'The camera could not open.' });
    return;
  }
  if (token !== openToken) {
    stopTracks(stream);
    return;
  }
  setState({ phase: 'preview', stream });
}

/** The second press: one frame from the preview, then the camera stops. Returns whether a picture was taken. */
export function takeLiveCallCameraPicture(video: HTMLVideoElement): boolean {
  if (state.phase !== 'preview') return false;
  const picture = cameraFrameFrom(video);
  stopTracks(state.stream);
  openToken += 1;
  if (!picture) {
    setState({ phase: 'error', stream: null, error: 'The picture could not be taken.' });
    return false;
  }
  frame = picture;
  setState({ phase: 'attached', stream: null, requested: null, error: null });
  return true;
}

/** Closes the preview or drops the waiting picture; the camera is off afterwards. */
export function closeLiveCallCamera(): void {
  openToken += 1;
  stopTracks(state.stream);
  frame = null;
  setState({ phase: 'off', stream: null, requested: null, error: null });
}

/** The waiting picture, for the turn being sent; it goes with one turn only. */
export function takeLiveCallCameraFrame(): string | null {
  const picture = frame;
  frame = null;
  if (state.phase === 'attached') setState({ phase: 'off' });
  return picture;
}

/** The call asked to see something (a `camera_request` event): Show is shown prominently. Nothing is opened. */
export function noteLiveCallCameraRequest(what: string): void {
  if (!state.available) return;
  setState({ requested: what.trim() || 'something' });
}

/** Reads whether this chat's call may offer Show. Nothing is sent to a model. */
export async function refreshLiveCallCameraAvailability(sessionId: string): Promise<void> {
  const token = ++availabilityToken;
  let available = false;
  try {
    const data = await unwrap(api.GET('/api/chat/sessions/{session_id}/live-call/camera', {
      params: { path: { session_id: sessionId } },
      cache: 'no-store',
    }));
    available = data.available === true;
  } catch {
    available = false;
  }
  if (token !== availabilityToken) return;
  setState({ available, availabilitySessionId: sessionId });
  if (!available && state.phase !== 'off') closeLiveCallCamera();
}

/** A call starts or ends: the camera is off and any picture dropped. Show reads availability again itself. */
export function resetLiveCallCamera(): void {
  closeLiveCallCamera();
}

/** One JPEG frame from a playing camera video, its longest side at most `longestSide`; null when none can be taken. */
export function cameraFrameFrom(video: HTMLVideoElement, longestSide = LIVE_CALL_CAMERA_LONGEST_SIDE): string | null {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return null;
  const scale = Math.min(1, longestSide / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext('2d');
  if (!context) return null;
  try {
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const picture = canvas.toDataURL('image/jpeg', LIVE_CALL_CAMERA_JPEG_QUALITY);
    return picture.startsWith('data:image/jpeg') ? picture : null;
  } catch {
    return null;
  }
}

export function resetLiveCallCameraForTests(): void {
  stopTracks(state.stream);
  frame = null;
  openToken += 1;
  availabilityToken += 1;
  state = initialState();
  listeners.forEach((listener) => listener());
}
