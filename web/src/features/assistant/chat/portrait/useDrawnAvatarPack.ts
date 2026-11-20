import { useMemo, useSyncExternalStore } from 'react';
import type { CharacterAvatarPack } from '../characterClient';
import { drawnAvatarPack } from '../liveCharacterAvatarBridge';
import { livePortrait, portraitEnabled, portraitNotice, type LivePortraitSnapshot } from './livePortrait';

const NOT_STREAMING: LivePortraitSnapshot = { status: 'off', fallbackRenderer: 'orb', reason: null };

/**
 * What a call's visual draws for its avatar pack, the same in the call panel and in fullscreen: a portrait while it can
 * show, the pack's fallback when it cannot, and why (`notice`). On a group call the live portrait is the speaker's
 * (`memberId`, null for the chat's own character): for every other member it is not streaming (`mine` false).
 */
export function useDrawnAvatarPack(avatarPack: CharacterAvatarPack | null | undefined, memberId: string | null = null) {
  const snapshot = useSyncExternalStore(livePortrait.subscribe, livePortrait.getSnapshot, livePortrait.getSnapshot);
  const mine = (snapshot.speakerId ?? null) === memberId;
  const portraitState = mine ? snapshot : NOT_STREAMING;
  const portraitUnavailable = portraitState.status === 'unavailable' || portraitState.status === 'degraded'
    || portraitState.status === 'loading' || !portraitEnabled();
  const pack = useMemo(() => drawnAvatarPack(avatarPack, portraitUnavailable), [avatarPack, portraitUnavailable]);
  return { pack, portraitState, notice: portraitNotice(portraitState), mine };
}
