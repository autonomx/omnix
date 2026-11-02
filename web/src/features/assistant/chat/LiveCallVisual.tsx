import { useEffect, useMemo, useRef } from 'react';
import {
  avatarBackgroundImage,
  avatarCaption,
  avatarFrameAsset,
  avatarPresentationState,
  characterAvatarAssetUrl,
  useLiveAvatar,
} from './liveCharacterAvatarBridge';
import { LiveVoiceOrb } from './LiveVoiceOrb';
import { AvatarLoadingNotice, LivePortraitCanvas } from './portrait/LivePortraitCanvas';
import { useDrawnAvatarPack } from './portrait/useDrawnAvatarPack';
import { CHARACTER_LIVE2D_RENDER_EVENT, emitOmnixEvent } from '../../../events/bus';


/**
 * The live call's visual: the character avatar when the session has one (a
 * live portrait, a sprite frame, or a host for the Live2D renderer), the voice
 * orb otherwise. A portrait that is unavailable shows its pack's fallback.
 */
export function LiveCallVisual({ voiceMode, thinking, runtimeLoading = false }: {
  voiceMode: string;
  thinking: boolean;
  /** The session's runtime, which names its avatar, is still on its way. */
  runtimeLoading?: boolean;
}) {
  const avatar = useLiveAvatar();
  const runtime = avatar.runtime;
  const { pack, portraitState, notice } = useDrawnAvatarPack(runtime?.avatar_pack);
  const portrait = pack?.renderer === 'portrait' && Boolean(pack.base_asset_id);
  const live2d = pack?.renderer === 'live2d' && Boolean(pack.rig_asset_id);
  const state = avatarPresentationState(avatar.mouthFrame, voiceMode, thinking);
  const assetId = live2d || portrait ? '' : avatarFrameAsset(pack, avatar, state);
  const showAvatar = Boolean(runtime && (portrait || live2d || assetId));
  const live2dHostRef = useRef<HTMLElement | null>(null);
  // A portrait pack's Live2D fallback is drawn from the pack as a Live2D one.
  const live2dRuntime = useMemo(
    () => (runtime && pack && pack !== runtime.avatar_pack ? { ...runtime, avatar_pack: pack } : runtime),
    [runtime, pack],
  );

  useEffect(() => {
    if (!live2d || !live2dRuntime || !live2dHostRef.current) return;
    emitOmnixEvent(CHARACTER_LIVE2D_RENDER_EVENT, { runtime: live2dRuntime, host: live2dHostRef.current });
  }, [live2d, live2dRuntime]);

  return (
    <div
      key={live2d && pack ? `${pack.character_id}:${pack.version}:${pack.rig_asset_id}` : 'voice-orb'}
      className="assistant-live-visual-stage"
      role="img"
      aria-label="Live character visual"
      data-has-character-avatar={showAvatar ? 'true' : undefined}
    >
      {showAvatar && runtime && pack ? (
        portrait ? (
          <figure className="assistant-live-character-avatar" data-renderer="portrait" data-portrait-status={portraitState.status} data-voice-mode={state} style={{ backgroundImage: avatarBackgroundImage(pack) || undefined }}>
            <LivePortraitCanvas
              key={portraitState.status === 'off' ? 'idle' : 'call'}
              imageUrl={characterAvatarAssetUrl(pack.base_asset_id ?? '')}
              label={`${runtime.display_name} live portrait`}
            />
            <figcaption>{avatarCaption(runtime.display_name, state)}</figcaption>
          </figure>
        ) : live2d ? (
          <figure ref={live2dHostRef} className="assistant-live-character-avatar" data-renderer="live2d" data-mouth-frame={avatar.mouthFrame} data-voice-mode={state} />
        ) : (
          <figure className="assistant-live-character-avatar" data-renderer="sprite" data-mouth-frame={avatar.mouthFrame} data-voice-mode={state} style={{ backgroundImage: avatarBackgroundImage(pack) || undefined }}>
            <img src={characterAvatarAssetUrl(assetId)} alt={`${runtime.display_name} live avatar`} />
            <figcaption>{avatarCaption(runtime.display_name, state)}</figcaption>
          </figure>
        )
      ) : (
        <LiveVoiceOrb voiceMode={voiceMode} />
      )}
      {notice ? <p className="assistant-live-portrait-notice" role="status">{notice}</p> : null}
      {!notice && runtimeLoading && !showAvatar ? <AvatarLoadingNotice /> : null}
    </div>
  );
}
