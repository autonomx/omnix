 
import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import {
  selectLiveChatSnapshot,
  useLiveConversationState,
} from '../workspace/live-conversation-store';
import {
  exitLiveChatFullscreen,
  useLiveChatFullscreenState,
} from './live-chat-fullscreen-controller';
import { Live2DZoomControl } from './Live2DZoomControl';
import { Live2DMotionControl } from './Live2DMotionControl';
import { readLatestTrustedCharacterRuntime, type CharacterAvatarPack, type CharacterLiveCallRuntime } from './characterClient';
import { avatarBackgroundImage, avatarFrameAsset, avatarPresentationState, characterAvatarAssetUrl, useLiveAvatar, type LiveAvatarState } from './liveCharacterAvatarBridge';
import { LiveCallScene } from './LiveCallScene';
import { LiveCallTaskChips } from './LiveCallTaskChips';
import { LiveMuteButton } from './LiveMuteButton';
import { LiveQuietButton } from './LiveQuietButton';
import { LiveShowButton } from './LiveShowButton';
import { MemberPortrait } from './portrait/MemberPortrait';
import { loadMemberLoop } from './portrait/memberIdleLoops';
import { useDrawnAvatarPack } from './portrait/useDrawnAvatarPack';
import { useLiveCallPresentation } from '../workspace/live-call-presentation-store';
import { callSceneGuests, useCallScene } from '../workspace/live-call-scene';
import './LiveChatFullscreenShell.css';
import { CHARACTER_AVATAR_RUNTIME_EVENT, CHARACTER_LIVE2D_RENDER_EVENT, emitOmnixEvent } from '../../../events/bus';


/** A message of the conversation shown in immersive Live Chat. */
export type LiveChatMessage = {
  id: string;
  role: 'assistant' | 'user' | 'system';
  text: string;
  timestamp: string | null;
  /** The call guest who spoke a reply (companion 5.6); a reply without one is the chat's own character's. */
  speaker?: string | null;
};

export type LiveChatFullscreenShellProps = {
  /** The conversation, newest last (Chat passes its messages or the live transcript). */
  messages: readonly LiveChatMessage[];
  /** Sends through Chat's composer; false when nothing was sent. */
  onSendMessage: (text: string) => boolean;
  /** Starts or ends the live call. */
  onToggleCall: () => void;
};

/** The call card's line about the microphone. */
function microphoneStatusLabel(
  snapshot: ReturnType<typeof selectLiveChatSnapshot>,
  conversation: ReturnType<typeof useLiveConversationState>['conversation'],
  muted: boolean,
): string {
  if (!snapshot.connected) return 'Microphone offline';
  if (muted) return 'Microphone muted';
  if (conversation.assistantTurn === 'speaking' && snapshot.duplexMode === 'half_duplex') return 'Microphone paused during playback';
  return conversation.userTurn === 'speaking' ? 'Hearing you' : 'Microphone listening';
}

export function LiveChatFullscreenShell({ messages, onSendMessage, onToggleCall }: LiveChatFullscreenShellProps) {
  const fullscreen = useLiveChatFullscreenState();
  const runtime = useLiveConversationState();
  const presentation = useLiveCallPresentation();
  const snapshot = selectLiveChatSnapshot(runtime);
  const [characterRuntime, setCharacterRuntime] = useState<CharacterLiveCallRuntime | null>(() => readLatestTrustedCharacterRuntime());
  const [composerText, setComposerText] = useState('');
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const shellRef = useRef<HTMLElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!fullscreen.immersive) return;
    const handleRuntime = (event: Event) => {
      setCharacterRuntime((event as CustomEvent<CharacterLiveCallRuntime | null>).detail ?? null);
    };
    window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, handleRuntime);
    setCharacterRuntime(readLatestTrustedCharacterRuntime());
    return () => window.removeEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, handleRuntime);
  }, [fullscreen.immersive]);

  useEffect(() => {
    if (!fullscreen.immersive) return;
    shellRef.current?.focus({ preventScroll: true });
  }, [fullscreen.immersive]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript || !fullscreen.immersive) return;
    transcript.scrollTop = transcript.scrollHeight;
  }, [fullscreen.immersive, messages, runtime.transcript.partial]);

  const stageMode = useMemo(() => {
    const conversation = runtime.conversation;
    if (conversation.connection === 'connecting') return 'connecting';
    if (conversation.connection === 'disconnected') return 'idle';
    if (conversation.bargeIn === 'ducking' || conversation.bargeIn === 'confirming') return 'yielding';
    if (conversation.assistantTurn === 'speaking' || conversation.delivery === 'audio_started') return 'speaking';
    if (conversation.assistantTurn === 'planning' || conversation.assistantTurn === 'generating') return 'thinking';
    if (conversation.userTurn === 'speaking' || conversation.floorOwner === 'user') return 'listening';
    return 'ready';
  }, [runtime.conversation]);

  if (!fullscreen.immersive || typeof document === 'undefined') return null;

  const microphoneStatus = microphoneStatusLabel(snapshot, runtime.conversation, presentation.micMuted);
  const duplexLabel = snapshot.duplexMode === 'echo_aware' ? 'Echo-aware' : 'Safe half-duplex';
  const displayIdentity = characterRuntime?.display_name?.trim() || snapshot.identity;

  function toggleCall(): void {
    onToggleCall();
    setActionStatus(snapshot.connected ? 'Ending live call…' : 'Starting live call…');
  }

  function submitMessage(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!composerText.trim()) return;
    if (!onSendMessage(composerText)) return;
    setComposerText('');
    setActionStatus('Message sent through the current chat session.');
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  return createPortal(
    <section
      ref={shellRef}
      className={`live-chat-fullscreen-shell mode-${stageMode}`}
      data-live-chat-fullscreen-shell
      role="dialog"
      aria-modal="true"
      aria-label={`Immersive Live Chat with ${displayIdentity}`}
      tabIndex={-1}
    >
      <div className="live-chat-fullscreen-topbar">
        <div className="live-chat-fullscreen-brand">
          <span aria-hidden="true">✦</span>
          <div><strong>Omnix Live</strong><small>Immersive conversation</small></div>
        </div>
        <div className="live-chat-fullscreen-topbar-actions">
          <span className={snapshot.connected ? 'connected' : undefined}>
            <i aria-hidden="true" />{snapshot.connected ? `Live with ${snapshot.identity}` : 'Call idle'}
          </span>
          <button type="button" onClick={() => void exitLiveChatFullscreen()} aria-label="Exit fullscreen Live Chat">Exit fullscreen</button>
        </div>
      </div>

      <main className="live-chat-fullscreen-layout">
        <LiveCharacterStage
          speaking={presentation.speaking} speakerId={presentation.sceneSpeakerId}
          sessionId={runtime.sessionId}
          identity={displayIdentity}
          status={snapshot.state} stageMode={stageMode}
          characterRuntime={characterRuntime}
        />

        <aside className="live-chat-fullscreen-rail" aria-label="Live conversation">
          <header>
            <div><p className="eyebrow">Private conversation</p><h1>Talk with {displayIdentity}</h1></div>
            <span>{fullscreen.browserState === 'active' ? 'Browser fullscreen' : 'Immersive view'}</span>
          </header>

          <div className="live-chat-fullscreen-transcript" role="log" aria-live="polite" ref={transcriptRef}>
            {messages.length ? messages.slice(-24).map((message) => (
              <article className={message.role} key={message.id}>
                <header><strong>{message.role === 'user' ? 'You' : message.role === 'assistant' ? message.speaker || displayIdentity : 'System'}</strong>{message.timestamp ? <time dateTime={message.timestamp}>{formatTime(message.timestamp)}</time> : null}</header>
                <p>{message.text}</p>
              </article>
            )) : (
              <div className="live-chat-fullscreen-empty">
                <span aria-hidden="true">✦</span>
                <p>Your conversation will appear here. Start the call or send a message.</p>
              </div>
            )}
            {runtime.transcript.partial ? (
              <article className="user partial"><header><strong>You</strong><span>Listening…</span></header><p>{runtime.transcript.partial}</p></article>
            ) : null}
          </div>

          <section className="live-chat-fullscreen-call-card" aria-label="Live voice controls">
            <div>
              <strong>Live voice</strong>
              <span>{microphoneStatus} · {duplexLabel}</span>
            </div>
            <div className="live-chat-fullscreen-call-buttons">
              <LiveMuteButton />
              <LiveQuietButton />
              <LiveShowButton />
              <button className={snapshot.connected ? 'danger' : undefined} type="button" onClick={toggleCall}>
                <span aria-hidden="true">{snapshot.connected ? '■' : '●'}</span>
                {snapshot.connected ? 'End voice chat' : 'Start voice chat'}
              </button>
            </div>
            <LiveCallScene sessionId={runtime.sessionId} />
            <LiveCallTaskChips />
            <small>{snapshot.state}. You can interrupt naturally when echo-aware mode is active.</small>
          </section>

          <form className="live-chat-fullscreen-composer" onSubmit={submitMessage}>
            <label>
              <span>Message {displayIdentity}</span>
              <textarea
                rows={2}
                value={composerText}
                placeholder="Write a message…"
                onChange={(event) => setComposerText(event.currentTarget.value)}
                onKeyDown={handleComposerKeyDown}
              />
            </label>
            <button type="submit" aria-label="Send fullscreen Live Chat message" disabled={!composerText.trim()}>➤</button>
          </form>

          <footer>
            <span>{actionStatus ?? 'Audio and conversation state remain owned by the current Live Chat session.'}</span>
            <button type="button" onClick={() => void exitLiveChatFullscreen()}>Return to Live Chat settings</button>
          </footer>
        </aside>
      </main>
    </section>,
    document.body,
  );
}

function LiveCharacterStage({
  speaking,
  speakerId,
  sessionId,
  identity,
  status,
  stageMode,
  characterRuntime,
}: {
  speaking: boolean;
  /** The call member speaking the current reply; none is the chat's own character. */
  speakerId: string | null;
  sessionId: string | null;
  identity: string;
  status: string;
  stageMode: string;
  characterRuntime: CharacterLiveCallRuntime | null;
}) {
  const liveAvatar = useLiveAvatar();
  const scene = useCallScene();
  // The runtime may be on its way when fullscreen opens; the avatar on screen is drawn from what the panel has.
  const shownRuntime = characterRuntime ?? liveAvatar.runtime;
  // Everyone on the call gets a tile, as in a video call; a guest's face comes from the runtime read after it joined.
  const guests = sessionId && scene.sessionId === sessionId ? callSceneGuests(scene) : [];
  const guestRuntime = scene.guests ?? shownRuntime?.scene_guests ?? [];
  const guestSpeaking = speaking && guests.some((guest) => guest.character_id === speakerId);
  // The reply's audio moves the speaker's mouth, not the host's.
  const live = guestSpeaking ? { ...liveAvatar, mouthFrame: 'closed' as const } : liveAvatar;
  const hostSpeaking = speaking && !guestSpeaking;
  const { pack, portraitState, notice, mine } = useDrawnAvatarPack(shownRuntime?.avatar_pack);
  const isPortrait = pack?.renderer === 'portrait' && Boolean(pack.base_asset_id);
  const voiceMode = hostSpeaking ? 'speaking' : stageMode === 'listening' ? 'listening' : 'idle';
  const presentationState = avatarPresentationState(live.mouthFrame, voiceMode, stageMode === 'thinking');
  const assetId = avatarFrameAsset(pack, live, presentationState);
  const avatar = {
    imageUrl: assetId ? characterAvatarAssetUrl(assetId) : null,
    alt: `${identity} live avatar`,
    backgroundImage: avatarBackgroundImage(pack),
    mouthFrame: live.mouthFrame,
    voiceMode: presentationState,
  };
  const initial = identity.trim().charAt(0).toLocaleUpperCase() || 'O';
  const stageStyle = avatar.backgroundImage ? { backgroundImage: avatar.backgroundImage } : undefined;
  const live2dHostRef = useRef<HTMLElement | null>(null);
  const isLive2D = pack?.renderer === 'live2d' && Boolean(pack.rig_asset_id);
  // A portrait pack's Live2D fallback is drawn from the pack as a Live2D one.
  const live2dRuntime = useMemo(
    () => (shownRuntime && pack && pack !== shownRuntime.avatar_pack ? { ...shownRuntime, avatar_pack: pack } : shownRuntime),
    [shownRuntime, pack],
  );

  // Every portrait member idles live while another speaks: each one's loop is asked for once it is on the call.
  const hostId = shownRuntime?.avatar_pack?.renderer === 'portrait' ? shownRuntime.avatar_pack.character_id : null;
  const portraitGuestIds = guests
    .filter((guest) => guestRuntime.find((entry) => entry.character_id === guest.character_id)?.avatar_pack?.renderer === 'portrait')
    .map((guest) => guest.character_id)
    .join(',');
  useEffect(() => {
    if (!sessionId || !portraitGuestIds) return;
    if (hostId) void loadMemberLoop(sessionId, hostId, null);
    for (const guestId of portraitGuestIds.split(',')) void loadMemberLoop(sessionId, guestId, guestId);
  }, [sessionId, hostId, portraitGuestIds, speakerId]);

  useEffect(() => {
    if (!isLive2D || !live2dRuntime || !live2dHostRef.current) return;
    emitOmnixEvent(CHARACTER_LIVE2D_RENDER_EVENT, { runtime: live2dRuntime, host: live2dHostRef.current });
  }, [live2dRuntime, isLive2D]);

  const hostAvatar = (
    <div className="live-chat-stage-avatar" data-mouth-frame={avatar.mouthFrame} data-voice-mode={avatar.voiceMode}>
      {isPortrait ? (
        <figure className="assistant-live-character-avatar" data-renderer="portrait" data-portrait-status={portraitState.status}>
          <MemberPortrait
            characterId={pack?.character_id}
            live={mine}
            streaming={portraitState.status !== 'off'}
            imageUrl={characterAvatarAssetUrl(pack?.base_asset_id ?? '')}
            label={`${identity} live portrait`}
          />
        </figure>
      ) : isLive2D ? <figure ref={live2dHostRef} className="assistant-live-character-avatar" data-renderer="live2d" aria-label={`${identity} Live2D avatar`} /> : avatar.imageUrl ? <img src={avatar.imageUrl} alt={avatar.alt} /> : <div role="img" className="live-chat-stage-fallback" aria-label={`${identity} visual placeholder`}><span>{initial}</span><i aria-hidden="true" /></div>}
      {notice ? <p className="assistant-live-portrait-notice" role="status">{notice}</p> : null}
    </div>
  );

  return (
    <section className="live-chat-character-stage" style={stageStyle} aria-label={`${identity} character stage`}>
      <div className="live-chat-stage-stars" aria-hidden="true" />
      <header><div><p className="eyebrow">Live room</p><h2>{identity}</h2></div><span>{title(stageMode)}</span></header>
      {guests.length ? (
        <div className="live-chat-stage-room" data-members={guests.length + 1} aria-label="Call members" role="list">
          <div className="live-chat-stage-tile" role="listitem" data-role="host" data-speaking={hostSpeaking ? 'true' : undefined}>
            {hostAvatar}
            <span className="live-chat-stage-tile-name">{identity}</span>
          </div>
          {guests.map((guest) => (
            <LiveCallGuestTile
              key={guest.character_id}
              characterId={guest.character_id}
              name={guest.display_name}
              pack={guestRuntime.find((candidate) => candidate.character_id === guest.character_id)?.avatar_pack ?? null}
              speaking={speaking && guest.character_id === speakerId}
              avatar={liveAvatar}
            />
          ))}
        </div>
      ) : hostAvatar}
      {isLive2D ? <Live2DMotionControl rigAssetId={pack?.rig_asset_id} /> : null}
      {isLive2D ? <Live2DZoomControl /> : null}
      <div className="live-chat-stage-caption" aria-live="polite"><i aria-hidden="true" /><span>{status}</span></div>
      <footer><span>Character-first mode</span><span>{isPortrait ? 'Live portrait linked' : avatar.imageUrl ? 'Avatar animation linked' : 'System visual fallback'}</span></footer>
    </section>
  );
}

/**
 * A guest's tile. A portrait guest is live: the live portrait while its turn plays, its idle loop otherwise (its
 * picture until the loop is known), and its pack's fallback when its portrait cannot show. A sprite guest's mouth
 * follows the reply it is speaking; a Live2D guest shows its base picture, since one Live2D rig is driven at a time.
 */
function LiveCallGuestTile({
  characterId,
  name,
  pack,
  speaking,
  avatar,
}: {
  characterId: string;
  name: string;
  pack: CharacterAvatarPack | null;
  speaking: boolean;
  avatar: Pick<LiveAvatarState, 'mouthFrame' | 'blinkClosed'>;
}) {
  const drawn = useDrawnAvatarPack(pack, characterId);
  const portrait = drawn.pack?.renderer === 'portrait' && Boolean(drawn.pack.base_asset_id);
  const assetId = guestPictureAsset(drawn.pack, speaking ? avatar : { mouthFrame: 'closed', blinkClosed: false }, speaking);
  const initial = name.trim().charAt(0).toLocaleUpperCase() || '?';
  return (
    <div className="live-chat-stage-tile" role="listitem" data-role="guest" data-speaking={speaking ? 'true' : undefined}>
      <div className="live-chat-stage-tile-picture" data-renderer={portrait ? 'portrait' : undefined}>
        {portrait ? (
          <MemberPortrait
            characterId={characterId}
            live={drawn.mine}
            streaming={drawn.portraitState.status !== 'off'}
            imageUrl={characterAvatarAssetUrl(drawn.pack?.base_asset_id ?? '')}
            label={`${name} avatar`}
          />
        ) : assetId
          ? <img src={characterAvatarAssetUrl(assetId)} alt={`${name} avatar`} />
          : <div role="img" className="live-chat-stage-tile-initial" aria-label={`${name} visual placeholder`}><span>{initial}</span></div>}
      </div>
      <span className="live-chat-stage-tile-name">{name}{speaking ? <small> · speaking</small> : null}</span>
    </div>
  );
}

function guestPictureAsset(
  pack: CharacterAvatarPack | null,
  avatar: Pick<LiveAvatarState, 'mouthFrame' | 'blinkClosed'>,
  speaking: boolean,
): string {
  if (!pack) return '';
  if (pack.renderer === 'sprite') return avatarFrameAsset(pack, avatar, speaking ? 'speaking' : 'idle') || pack.base_asset_id || '';
  return pack.base_asset_id || '';
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function title(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toLocaleUpperCase());
}
