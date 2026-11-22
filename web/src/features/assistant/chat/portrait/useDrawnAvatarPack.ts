import { useMemo, useSyncExternalStore } from 'react';
import type { CharacterAvatarPack } from '../characterClient';
import { avatarMouthAssetForFrame, drawnAvatarPack } from '../liveCharacterAvatarBridge';
import { livePortrait, portraitEnabled, portraitNotice, type LivePortraitSnapshot } from './livePortrait';
import { packRevision, useMemberLoop } from './memberIdleLoops';

const NOT_STREAMING: LivePortraitSnapshot = { status: 'off', fallbackRenderer: 'orb', reason: null };

/**
 * What a call's visual draws for its avatar pack, the same in the call panel and in fullscreen: a portrait while it can
 * show, the pack's fallback when it cannot, and why (`notice`). On a group call the live portrait is the speaker's
 * (`memberId`, null for the chat's own character): for every other member it is not streaming (`mine` false).
 *
 * A fallback that is only the pack's picture is the same face as the portrait's idle loop, but uncropped: shown in its
 * place, the tile changed size and went still each time the portrait fell behind (a group call's guest whose voice
 * barely runs ahead of playback, 2026-11-21). So a member whose loop is known idles on it instead (`mine` false: its
 * stream is not drawn), with the same notice; a fallback that moves (a sprite's mouth, Live2D, the orb) is kept.
 */
export function useDrawnAvatarPack(avatarPack: CharacterAvatarPack | null | undefined, memberId: string | null = null) {
  const snapshot = useSyncExternalStore(livePortrait.subscribe, livePortrait.getSnapshot, livePortrait.getSnapshot);
  const mine = (snapshot.speakerId ?? null) === memberId;
  const portraitState = mine ? snapshot : NOT_STREAMING;
  const cannotStream = portraitState.status === 'unavailable' || portraitState.status === 'degraded'
    || portraitState.status === 'loading';
  const enabled = portraitEnabled();
  const portraitPack = avatarPack?.renderer === 'portrait' ? avatarPack : null;
  const loop = useMemberLoop(portraitPack?.character_id, packRevision(portraitPack));
  const idles = cannotStream && enabled && Boolean(loop) && stillFallback(portraitPack);
  const portraitUnavailable = (cannotStream || !enabled) && !idles;
  const pack = useMemo(() => drawnAvatarPack(avatarPack, portraitUnavailable), [avatarPack, portraitUnavailable]);
  return { pack, portraitState, notice: portraitNotice(portraitState), mine: mine && !idles };
}

/** Whether a portrait pack's fallback shows only its picture: a sprite with no mouth to move. */
function stillFallback(pack: CharacterAvatarPack | null): boolean {
  if (!pack || pack.fallback_renderer !== 'sprite') return false;
  const picture = pack.base_asset_id || '';
  return (['small', 'medium', 'wide'] as const).every((frame) => avatarMouthAssetForFrame(pack, frame) === picture);
}
