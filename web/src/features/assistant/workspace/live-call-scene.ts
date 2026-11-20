import { useSyncExternalStore } from 'react';

import { ApiError } from '../../../api/errors';
import { unwrap } from '../../../api/http';
import { api } from '../api/gateway';
import type { components } from '../api/generated';
import { characterClient } from '../chat/characterClient';

/**
 * Who is on a character call (live companion roadmap 5.5/5.6): the host and up to four guests. The server owns the
 * seats and decides who speaks each turn; this module mirrors the members for the call panel, and maps a turn's
 * speaker (the `X-Omnix-Scene-Speaker` header) to that member's voice.
 */
export type CallSceneView = components['schemas']['SceneView'];
export type CallSceneMember = components['schemas']['SceneMemberView'];
export type CallSceneGuest = components['schemas']['LiveCallSceneGuest'];

/** The member a scene turn speaks as, when it is not the host. */
export const SCENE_SPEAKER_HEADER = 'X-Omnix-Scene-Speaker';
/** The proactive reason that asks whether another member reacts to the reply just heard. */
export const SCENE_REACTION_REASON = 'scene_reaction';
/** The reasons that ask for the next line between members, and for a member to start them talking (companion 6.4). */
export const SCENE_LINE_REASON = 'scene_line';
export const SCENE_TALK_REASON = 'scene_talk';
/** How long the call must be quiet before a member starts talking, by the account's talk level (companion 6.1). */
export const SCENE_TALK_SILENCE_MS = { rarely: 90_000, sometimes: 45_000, often: 20_000 } as const;

/** A line or an opener: after it plays, the call asks for the next line. A reaction is a single turn. */
export function isSceneTalkReason(reason: string): boolean {
  return [SCENE_LINE_REASON, SCENE_TALK_REASON].some((prefix) => reason === prefix || reason.startsWith(`${prefix}:`));
}

/** A scene turn's id: its lease is the server's, and a turn the call drops before it plays gives it back. */
export function isSceneTurnId(turnId: string): boolean {
  return ['scene-reaction:', 'scene-line:', 'scene-talk:'].some((prefix) => turnId.startsWith(prefix));
}

export type CallSceneState = {
  sessionId: string | null;
  scene: CallSceneView | null;
  loading: boolean;
  /** The character being added or removed. */
  changing: string | null;
  error: string | null;
  /** The guests' voices and avatars as the call runtime last read them after a change; null until one is read. */
  guests: CallSceneGuest[] | null;
};

const EMPTY: CallSceneState = { sessionId: null, scene: null, loading: false, changing: null, error: null, guests: null };
let state: CallSceneState = EMPTY;
const listeners = new Set<() => void>();
let loadToken = 0;

function setState(change: Partial<CallSceneState>): void {
  state = { ...state, ...change };
  listeners.forEach((listener) => listener());
}

export const callSceneStore = {
  getState(): CallSceneState {
    return state;
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  resetForTests(): void {
    loadToken += 1;
    state = EMPTY;
    listeners.forEach((listener) => listener());
  },
};

export function useCallScene(): CallSceneState {
  return useSyncExternalStore(callSceneStore.subscribe, callSceneStore.getState, callSceneStore.getState);
}

export function callSceneGuests(current: CallSceneState = state): CallSceneMember[] {
  return current.scene?.members.filter((member) => member.role === 'guest') ?? [];
}

/** Whether the chat's call has a guest: only then can another member react to a reply. */
export function callSceneHasGuests(sessionId: string, current: CallSceneState = state): boolean {
  return current.sessionId === sessionId && callSceneGuests(current).length > 0;
}

/** Whether the panel has read this chat's scene and it has no guest: then a call's end has nothing to clear. */
export function callSceneKnownEmpty(sessionId: string, current: CallSceneState = state): boolean {
  return current.sessionId === sessionId && current.scene !== null && callSceneGuests(current).length === 0;
}

/** The names said on a chat's call, for speech recognition to listen for: its members', host included. */
export function callScenePhrases(sessionId: string, current: CallSceneState = state): string[] {
  if (current.sessionId !== sessionId || !current.scene) return [];
  return current.scene.members.map((member) => member.display_name.trim()).filter(Boolean);
}

export async function loadCallScene(sessionId: string): Promise<void> {
  const token = ++loadToken;
  if (state.sessionId !== sessionId) setState({ ...EMPTY, sessionId, loading: true });
  else setState({ loading: true, error: null });
  try {
    const scene = await unwrap(api.GET('/api/chat/sessions/{session_id}/scene', {
      params: { path: { session_id: sessionId } },
      cache: 'no-store',
    }));
    if (token === loadToken) setState({ scene: sceneOrNull(scene), loading: false });
  } catch (error) {
    if (token === loadToken) setState({ loading: false, error: errorText(error) });
  }
}

export async function addCallGuest(sessionId: string, characterId: string): Promise<void> {
  await changeScene(sessionId, characterId, () => unwrap(api.POST('/api/chat/sessions/{session_id}/scene/guests', {
    params: { path: { session_id: sessionId } },
    body: { character_id: characterId },
  })));
}

export async function removeCallGuest(sessionId: string, characterId: string): Promise<void> {
  await changeScene(sessionId, characterId, () => unwrap(api.DELETE('/api/chat/sessions/{session_id}/scene/guests/{character_id}', {
    params: { path: { session_id: sessionId, character_id: characterId } },
  })));
}

/**
 * The call ended: its guests leave, so the next call on this chat starts with the chat's own character alone. The
 * guests stay seated when the server could not be reached; the panel still shows them and they can be removed.
 */
export async function clearCallScene(sessionId: string): Promise<void> {
  const token = ++loadToken;
  try {
    const scene = await unwrap(api.DELETE('/api/chat/sessions/{session_id}/scene/guests', {
      params: { path: { session_id: sessionId } },
    }));
    if (token !== loadToken || state.sessionId !== sessionId) return;
    setState({ scene: sceneOrNull(scene), guests: [], error: null });
    await characterClient.refreshLiveCallRuntime(sessionId).catch(() => null);
  } catch (error) {
    if (token === loadToken && state.sessionId === sessionId) setState({ error: errorText(error) });
  }
}

async function changeScene(sessionId: string, characterId: string, request: () => Promise<CallSceneView>): Promise<void> {
  if (state.changing) return;
  const token = ++loadToken;
  setState({ sessionId, changing: characterId, error: null });
  try {
    const scene = await request();
    if (token !== loadToken) return;
    setState({ scene: sceneOrNull(scene), changing: null });
    // The runtime carries each guest's voice and avatar: the next turn a guest speaks must find it, and the
    // full-screen call shows the new guest's face.
    const runtime = await characterClient.refreshLiveCallRuntime(sessionId).catch(() => null);
    if (runtime && token === loadToken) setState({ guests: runtime.scene_guests ?? [] });
  } catch (error) {
    if (token === loadToken) setState({ changing: null, error: errorText(error) });
  }
}

/** The scene the server sent, or none when the body is not one (an older gateway, a proxy's page). */
function sceneOrNull(value: unknown): CallSceneView | null {
  const scene = value as CallSceneView | null;
  return scene && typeof scene === 'object' && Array.isArray(scene.members) ? scene : null;
}

/**
 * The voice a turn speaks in: the named guest's, else the call's own. A speaker the runtime does not list (the host,
 * or a guest added after the runtime was read) keeps the call's voice rather than guessing.
 */
export function sceneSpeakerVoiceId(
  speakerId: string | null,
  guests: readonly CallSceneGuest[] | null | undefined,
  callVoiceId: string | null,
): string | null {
  if (!speakerId) return callVoiceId;
  const guest = guests?.find((candidate) => candidate.character_id === speakerId);
  const voice = guest?.voice_speaker_id?.trim() || guest?.voice_asset_id?.trim();
  return voice || callVoiceId;
}

/** The speaker a response names, or null for the host (no header, or an empty one). */
export function sceneSpeakerFrom(response: Response): string | null {
  return response.headers.get(SCENE_SPEAKER_HEADER)?.trim() || null;
}

const SCENE_ERRORS: Record<string, string> = {
  scene_full: 'The call already has four guests.',
  host_is_already_in_the_call: 'That character is already hosting this call.',
  character_not_available: 'That character cannot join the call.',
  guest_not_found: 'That character is no longer on the call.',
  scene_needs_character_chat: 'Guests can join a character chat only.',
  scene_needs_postgresql: 'Guests need the database-backed chat store.',
};

function errorText(error: unknown): string {
  const message = error instanceof ApiError ? error.detail || error.body : error instanceof Error ? error.message : String(error);
  const code = Object.keys(SCENE_ERRORS).find((key) => message.includes(key));
  return code ? SCENE_ERRORS[code] : 'The call members could not be changed.';
}
