import { useSyncExternalStore } from 'react';

import { api } from '../../api/gateway';

/**
 * Every member of a group call stays live (companion 5.5): the portrait service streams one face at a time, the
 * speaker's, and the others play their portraits' idle loops. A member's loop comes from its own turn's stream (kept
 * by the live portrait) or, before that, from the gateway, which hands out only a loop the service has rendered
 * already while a call streams. The loops are kept as JPEG object URLs (a loop's frames as bitmaps would hold
 * about 150 MB a member), for one chat at a time.
 */
export type MemberIdleLoop = { frameMs: number; idle: string[]; blink: string[] };
export type MemberLoopBytes = { frameMs: number; idle: Uint8Array<ArrayBuffer>[]; blink: Uint8Array<ArrayBuffer>[] };

let sessionId: string | null = null;
let loops = new Map<string, MemberIdleLoop>();
// Members asked for, or refused for good (not a portrait, not on the call); a busy service may be asked again.
const asked = new Set<string>();
const listeners = new Set<() => void>();
let version = 0;

function notify(): void {
  version += 1;
  listeners.forEach((listener) => listener());
}

function forChat(chatSessionId: string): void {
  if (sessionId === chatSessionId) return;
  resetMemberLoops();
  sessionId = chatSessionId;
}

function toUrls(frames: readonly Uint8Array<ArrayBuffer>[]): string[] {
  return frames.map((frame) => URL.createObjectURL(new Blob([frame], { type: 'image/jpeg' })));
}

function store(characterId: string, loop: MemberLoopBytes): void {
  if (loop.frameMs <= 0 || loop.idle.length === 0) return;
  const previous = loops.get(characterId);
  loops = new Map(loops).set(characterId, { frameMs: loop.frameMs, idle: toUrls(loop.idle), blink: toUrls(loop.blink) });
  if (previous) revoke(previous);
  notify();
}

function revoke(loop: MemberIdleLoop): void {
  [...loop.idle, ...loop.blink].forEach((url) => URL.revokeObjectURL(url));
}

/** A member's loop as its own turn's stream sent it; the first one kept stands (they are the same portrait). */
export function rememberMemberLoop(chatSessionId: string, characterId: string, loop: MemberLoopBytes): void {
  forChat(chatSessionId);
  if (!loops.has(characterId)) store(characterId, loop);
}

/**
 * Ask the gateway for a member's loop, once (again only after a busy refusal); `speakerId` is null for the chat's
 * own character. A refusal leaves the member's picture in its tile.
 */
export async function loadMemberLoop(chatSessionId: string, characterId: string, speakerId: string | null): Promise<void> {
  forChat(chatSessionId);
  if (loops.has(characterId) || asked.has(characterId)) return;
  asked.add(characterId);
  try {
    const { data } = await api.GET('/api/tts/live-call/portrait-idle', {
      params: { query: { session_id: chatSessionId, ...(speakerId ? { speaker_id: speakerId } : {}) } },
      cache: 'no-store',
    });
    if (sessionId !== chatSessionId) return;
    if (!data?.ok) {
      if (!data || data.code === 'portrait_busy' || data.code === 'warming') asked.delete(characterId);
      return;
    }
    if (!loops.has(characterId)) store(characterId, { frameMs: data.frame_ms, idle: data.idle.map(decode), blink: data.blink.map(decode) });
  } catch {
    if (sessionId === chatSessionId) asked.delete(characterId);
  }
}

function decode(base64: string): Uint8Array<ArrayBuffer> {
  const text = atob(base64);
  const bytes = new Uint8Array(text.length);
  for (let index = 0; index < text.length; index += 1) bytes[index] = text.charCodeAt(index);
  return bytes;
}

export function memberLoop(characterId: string): MemberIdleLoop | null {
  return loops.get(characterId) ?? null;
}

export function resetMemberLoops(): void {
  loops.forEach(revoke);
  loops = new Map();
  asked.clear();
  sessionId = null;
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** A member's idle loop, once one is known; null until then. */
export function useMemberLoop(characterId: string | null | undefined): MemberIdleLoop | null {
  useSyncExternalStore(subscribe, () => version, () => version);
  return characterId ? memberLoop(characterId) : null;
}
