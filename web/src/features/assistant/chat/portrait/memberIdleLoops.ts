import { useSyncExternalStore } from 'react';

import { api } from '../../api/gateway';

/**
 * Every member of a group call stays live (companion 5.5): the portrait service streams one face at a time, the
 * speaker's, and the others play their portraits' idle loops. A member's loop comes from its own turn's stream (kept
 * by the live portrait) or, before that, from the gateway, which hands out only a loop the service has rendered
 * already while a call streams. The loops are kept as JPEG object URLs (a loop's frames as bitmaps would hold
 * about 150 MB a member), for one chat at a time. A loop belongs to the member's pack as it was (`packRevision`): a pack
 * changed mid-chat makes the member's loop be asked for again, and the old one is let go once the new one is known.
 */
export type MemberIdleLoop = { frameMs: number; idle: string[]; blink: string[] };
export type MemberLoopBytes = { frameMs: number; idle: Uint8Array<ArrayBuffer>[]; blink: Uint8Array<ArrayBuffer>[] };

let sessionId: string | null = null;
let loops = new Map<string, { revision: string; loop: MemberIdleLoop }>();
// Members (at a pack revision) asked for, or refused for good (not a portrait, not on the call); a busy service may be
// asked again.
const asked = new Set<string>();
// Guests whose loops "Load live video" has had rendered (or tried to), so a second button on screen does not again.
const rendered = new Set<string>();
const listeners = new Set<() => void>();
let version = 0;

/** A member's pack as its loop was drawn from: its version and its picture. */
export function packRevision(pack: { version?: number | null; base_asset_id?: string | null } | null | undefined): string {
  return pack ? `${pack.version ?? ''}:${pack.base_asset_id ?? ''}` : '';
}

const askKey = (characterId: string, revision: string) => `${characterId}\n${revision}`;

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

function store(characterId: string, revision: string, loop: MemberLoopBytes): void {
  if (loop.frameMs <= 0 || loop.idle.length === 0) return;
  const previous = loops.get(characterId);
  const kept = { frameMs: loop.frameMs, idle: toUrls(loop.idle), blink: toUrls(loop.blink) };
  loops = new Map(loops).set(characterId, { revision, loop: kept });
  if (previous) revoke(previous.loop);
  notify();
}

function known(characterId: string, revision: string): boolean {
  return loops.get(characterId)?.revision === revision;
}

function revoke(loop: MemberIdleLoop): void {
  [...loop.idle, ...loop.blink].forEach((url) => URL.revokeObjectURL(url));
}

/** A member's loop as its own turn's stream sent it; the first one kept for a pack revision stands (the same face). */
export function rememberMemberLoop(chatSessionId: string, characterId: string, loop: MemberLoopBytes, revision = ''): void {
  forChat(chatSessionId);
  if (!known(characterId, revision)) store(characterId, revision, loop);
}

/**
 * Ask the gateway for a member's loop, once (again only after a busy refusal, or with `again` when the loop has just
 * been rendered); `speakerId` is null for the chat's own character. A refusal leaves the member's picture in its tile.
 */
export async function loadMemberLoop(
  chatSessionId: string, characterId: string, speakerId: string | null, revision = '', { again = false } = {},
): Promise<void> {
  forChat(chatSessionId);
  const key = askKey(characterId, revision);
  if (again) asked.delete(key);
  if (known(characterId, revision) || asked.has(key)) return;
  asked.add(key);
  try {
    const { data } = await api.GET('/api/tts/live-call/portrait-idle', {
      params: { query: { session_id: chatSessionId, ...(speakerId ? { speaker_id: speakerId } : {}) } },
      cache: 'no-store',
    });
    if (sessionId !== chatSessionId) return;
    if (!data?.ok) {
      if (!data || data.code === 'portrait_busy' || data.code === 'warming') asked.delete(key);
      return;
    }
    if (!known(characterId, revision)) {
      store(characterId, revision, { frameMs: data.frame_ms, idle: data.idle.map(decode), blink: data.blink.map(decode) });
    }
  } catch {
    if (sessionId === chatSessionId) asked.delete(key);
  }
}

/**
 * Claims a guest's loop for rendering before the call: true once per member and pack revision in the chat, so only
 * one caller has the service render it. The gateway hands out only rendered loops, and a guest's is otherwise first
 * rendered by its own turn.
 */
export function claimGuestRender(chatSessionId: string, characterId: string, revision = ''): boolean {
  forChat(chatSessionId);
  const key = askKey(characterId, revision);
  if (known(characterId, revision) || rendered.has(key)) return false;
  rendered.add(key);
  return true;
}

/** Whether `claimGuestRender` would still claim this guest, without claiming it (the load's progress counts it). */
export function guestRenderPending(chatSessionId: string, characterId: string, revision = ''): boolean {
  if (sessionId !== chatSessionId) return true;
  return !known(characterId, revision) && !rendered.has(askKey(characterId, revision));
}

function decode(base64: string): Uint8Array<ArrayBuffer> {
  const text = atob(base64);
  const bytes = new Uint8Array(text.length);
  for (let index = 0; index < text.length; index += 1) bytes[index] = text.charCodeAt(index);
  return bytes;
}

/** A member's loop for its pack at `revision`; null while only an older pack's is known. */
export function memberLoop(characterId: string, revision = ''): MemberIdleLoop | null {
  const entry = loops.get(characterId);
  return entry && entry.revision === revision ? entry.loop : null;
}

export function resetMemberLoops(): void {
  loops.forEach((entry) => revoke(entry.loop));
  loops = new Map();
  asked.clear();
  rendered.clear();
  sessionId = null;
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** A member's idle loop, once one is known; null until then. */
export function useMemberLoop(characterId: string | null | undefined, revision = ''): MemberIdleLoop | null {
  useSyncExternalStore(subscribe, () => version, () => version);
  return characterId ? memberLoop(characterId, revision) : null;
}
