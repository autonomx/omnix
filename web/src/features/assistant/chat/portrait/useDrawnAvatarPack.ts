import { useMemo, useSyncExternalStore } from 'react';
import type { CharacterAvatarPack } from '../characterClient';
import { drawnAvatarPack } from '../liveCharacterAvatarBridge';
import { livePortrait, portraitEnabled, portraitNotice } from './livePortrait';

/**
 * What a call's visual draws for its avatar pack, the same in the call panel and in fullscreen: a portrait while it can
 * show, the pack's fallback when it cannot, and why (`notice`).
 */
export function useDrawnAvatarPack(avatarPack: CharacterAvatarPack | null | undefined) {
  const portraitState = useSyncExternalStore(livePortrait.subscribe, livePortrait.getSnapshot, livePortrait.getSnapshot);
  const portraitUnavailable = portraitState.status === 'unavailable' || portraitState.status === 'degraded'
    || portraitState.status === 'loading' || !portraitEnabled();
  const pack = useMemo(() => drawnAvatarPack(avatarPack, portraitUnavailable), [avatarPack, portraitUnavailable]);
  return { pack, portraitState, notice: portraitNotice(portraitState) };
}
