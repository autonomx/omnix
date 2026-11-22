import { useSyncExternalStore } from 'react';

import { unwrap } from '../../../api/http';
import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT } from '../../../events/bus';
import { api } from '../api/gateway';
import { cameraFrameFrom } from './live-call-camera';
import { liveConversationStore } from './live-conversation-store';

/**
 * The shared front camera (camera share, 2026-11-21): like the shared screen, it stays on until the person turns it
 * off, in live calls and typed chat. Only the person's press opens it. While it is on, one frame goes to the gateway
 * as the person begins (a glance): when their speech is confirmed in a call, and before a turn whose chat has no
 * recent glance. The vision model describes it in the background and the turn says `camera_shared`, so the reply
 * never waits on a picture. The gateway keeps only the description, never the image.
 */
export type CameraSharePhase = 'off' | 'opening' | 'on' | 'error';

export type CameraShareState = {
  phase: CameraSharePhase;
  /** The open camera's stream, for the self-view, while it is on. */
  stream: MediaStream | null;
  error: string | null;
};

/** A glance's longest side: enough for a face and what is held up, quick for the vision model. */
export const CAMERA_SHARE_LONGEST_SIDE = 768;
/** A turn whose chat had no glance this recently sends one first. */
export const CAMERA_SHARE_TURN_FRESH_MS = 15_000;
/** Glances on speech are at most this often. */
export const CAMERA_SHARE_MIN_GLANCE_MS = 4_000;
/** Typing glances at most this often: keystrokes come many to a message. */
export const CAMERA_SHARE_TYPING_GAP_MS = 10_000;

type GlanceStatus = 'started' | 'in_progress' | 'vision_not_configured' | 'remote_vision_not_allowed' | 'vision_unavailable';

const UNAVAILABLE: Record<string, string> = {
  vision_not_configured: 'No vision model is set up, so the assistant cannot see the camera.',
  remote_vision_not_allowed: 'The camera picture would go to a remote model (Claude or Codex); allow remote vision in Settings → Assistant & Chat → Desktop Companion ("Allow remote vision provider") to share it.',
  vision_unavailable: 'The vision model is unavailable, so the assistant cannot see the camera.',
};

let state: CameraShareState = { phase: 'off', stream: null, error: null };
let video: HTMLVideoElement | null = null;
let openToken = 0;
// The chat and time of the last glance sent.
let lastGlance: { sessionId: string; at: number } | null = null;
const listeners = new Set<() => void>();

function setState(change: Partial<CameraShareState>): void {
  state = { ...state, ...change };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function cameraShareState(): CameraShareState {
  return state;
}

export function useCameraShare(): CameraShareState {
  return useSyncExternalStore(subscribe, cameraShareState, cameraShareState);
}

export function cameraShared(): boolean {
  return state.phase === 'on' && video !== null;
}

export async function toggleCameraShare(): Promise<void> {
  if (state.phase === 'on' || state.phase === 'opening') {
    stopCameraShare();
    return;
  }
  await startCameraShare();
}

/** Opens the front camera, video only, and keeps it shared until it is stopped. */
export async function startCameraShare(): Promise<void> {
  if (state.phase === 'on' || state.phase === 'opening') return;
  const token = ++openToken;
  setState({ phase: 'opening', error: null });
  let stream: MediaStream;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser has no camera access.');
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
  } catch (error) {
    if (token !== openToken) return;
    const denied = error instanceof DOMException && error.name === 'NotAllowedError';
    setState({ phase: 'error', stream: null, error: denied ? 'Camera access was not allowed.' : 'The camera could not open.' });
    return;
  }
  if (token !== openToken) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
  const element = document.createElement('video');
  element.muted = true;
  element.playsInline = true;
  element.srcObject = stream;
  void element.play?.()?.catch?.(() => undefined);
  video = element;
  lastGlance = null;
  stream.getVideoTracks()[0]?.addEventListener('ended', () => stopCameraShare(), { once: true });
  window.addEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, glanceOnSpeech);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, glanceOnSpeech);
  setState({ phase: 'on', stream, error: null });
}

export function stopCameraShare(): void {
  openToken += 1;
  window.removeEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, glanceOnSpeech);
  window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, glanceOnSpeech);
  state.stream?.getTracks().forEach((track) => track.stop());
  if (video) video.srcObject = null;
  video = null;
  lastGlance = null;
  setState({ phase: 'off', stream: null, error: null });
}

// The person speaking, or a call starting (its greeting and first turn then know what the camera shows).
function glanceOnSpeech(): void {
  const sessionId = liveConversationStore.getState().sessionId;
  if (sessionId) glanceAsPersonBegins(sessionId, CAMERA_SHARE_MIN_GLANCE_MS);
}

/** The person is typing a message in the selected chat: a glance, unless one was sent for it lately. */
export function glanceOnTyping(): void {
  const sessionId = liveConversationStore.getState().sessionId;
  if (sessionId) glanceAsPersonBegins(sessionId, CAMERA_SHARE_TYPING_GAP_MS);
}

function glanceAsPersonBegins(sessionId: string, minGapMs: number): void {
  if (!cameraShared()) return;
  const recent = lastGlance && lastGlance.sessionId === sessionId && Date.now() - lastGlance.at < minGapMs;
  if (!recent) void glanceCameraShare(sessionId);
}

/** Sends one frame for this chat's next turn. Returns whether it is being described. */
export async function glanceCameraShare(sessionId: string): Promise<boolean> {
  if (!cameraShared() || !video) return false;
  const image = cameraFrameFrom(video, CAMERA_SHARE_LONGEST_SIDE);
  if (!image) return false;
  lastGlance = { sessionId, at: Date.now() };
  let status: GlanceStatus;
  try {
    const data = await unwrap(api.POST('/api/chat/sessions/{session_id}/camera/glance', {
      params: { path: { session_id: sessionId } },
      body: { image },
    }));
    status = data.status as GlanceStatus;
  } catch {
    lastGlance = null;
    return false;
  }
  const unavailable = UNAVAILABLE[status];
  if (unavailable) {
    // The assistant cannot see the camera: it is turned off rather than left on unseen.
    stopCameraShare();
    setState({ phase: 'error', error: unavailable });
    return false;
  }
  return true;
}

/**
 * The fields a turn adds while the camera is shared. A chat without a recent glance sends one first, so the turn
 * finds a description being made; the reply itself never carries a picture.
 */
export async function cameraShareTurnFields(sessionId: string): Promise<{ camera_shared?: true }> {
  if (!cameraShared()) return {};
  const fresh = lastGlance && lastGlance.sessionId === sessionId && Date.now() - lastGlance.at < CAMERA_SHARE_TURN_FRESH_MS;
  if (!fresh && !(await glanceCameraShare(sessionId))) return cameraShared() ? { camera_shared: true } : {};
  return { camera_shared: true };
}

/** Clears an error shown after the camera stopped. */
export function dismissCameraShareError(): void {
  if (state.phase === 'error') setState({ phase: 'off', error: null });
}

export function resetCameraShareForTests(): void {
  stopCameraShare();
}
