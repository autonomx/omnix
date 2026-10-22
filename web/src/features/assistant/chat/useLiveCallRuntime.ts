import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { characterAvatarClient } from './characterAvatarClient';
import { characterClient, type CharacterLiveCallRuntime } from './characterClient';
import { publishCharacterAvatarRuntime, SYSTEM_ASSISTANT_AVATAR_ID } from './liveCharacterAvatarBridge';
import { NEUTRAL_SPEECH_STYLE, neutralSystemLiveCallRuntime } from './neutralLiveCallRuntime';
import type { ChatSessionListEntry } from './useChatSessions';
import { CHARACTER_AVATAR_RUNTIME_EVENT } from '../../../events/bus';

type LiveCallRuntimeOptions = {
  selectedSessionId: string | null;
  selectedSessionSummary: ChatSessionListEntry | undefined;
  interaction: Awaited<ReturnType<typeof characterClient.session>> | undefined;
  /** While a call runs, its runtime stays as the call started it. */
  liveVoiceActiveRef: RefObject<boolean>;
};

/** The live-call runtime (identity, voice, avatar, memory) of the selected session, preloaded before a call. */
export function useLiveCallRuntime({ selectedSessionId, selectedSessionSummary, interaction, liveVoiceActiveRef }: LiveCallRuntimeOptions) {
  const [liveCallRuntime, setLiveCallRuntime] = useState<CharacterLiveCallRuntime | null>(null);
  const liveCallRuntimeRef = useRef<CharacterLiveCallRuntime | null>(null);
  const liveCallRuntimeQuery = useQuery({
    queryKey: [
      'feature',
      'chatbot',
      'live-call-runtime',
      selectedSessionId,
      interaction?.interaction_mode,
      interaction?.character_id,
      interaction?.character_profile_version,
    ],
    queryFn: () => characterClient.liveCallRuntime(selectedSessionId ?? ''),
    // Runtime preload carries the identity's avatar, voice and memory, so the right rail shows the selected
    // character (or the System Assistant's own avatar) before a call starts. In a system chat it is a light read.
    enabled: Boolean(
      selectedSessionId
      && (selectedSessionSummary?.interaction_mode ?? 'system') === (interaction?.interaction_mode ?? 'system'),
    ),
  });

  useEffect(() => {
    if (!liveCallRuntimeQuery.data || liveVoiceActiveRef.current) return;
    liveCallRuntimeRef.current = liveCallRuntimeQuery.data;
    setLiveCallRuntime(liveCallRuntimeQuery.data);
  }, [liveCallRuntimeQuery.data, liveVoiceActiveRef]);

  // Before the first chat there is no session and so no runtime: the System Assistant's own avatar still shows, on a
  // neutral runtime the live view alone uses (a call loads its session's runtime). The key is the avatar panel's, so
  // choosing an avatar in Settings refreshes it.
  const assistantPackQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'character-avatar-pack', SYSTEM_ASSISTANT_AVATAR_ID],
    queryFn: () => characterAvatarClient.optionalPack(SYSTEM_ASSISTANT_AVATAR_ID),
    enabled: !selectedSessionId,
    retry: false,
  });
  useEffect(() => {
    if (selectedSessionId || liveVoiceActiveRef.current) return;
    const pack = assistantPackQuery.data ?? null;
    const preview = pack ? { ...neutralSystemLiveCallRuntime('', null, NEUTRAL_SPEECH_STYLE), avatar_pack: pack } : null;
    liveCallRuntimeRef.current = preview;
    setLiveCallRuntime(preview);
    publishCharacterAvatarRuntime(preview);
  }, [assistantPackQuery.data, selectedSessionId, liveVoiceActiveRef]);

  useEffect(() => {
    const runtime = liveCallRuntimeRef.current;
    if (!runtime || !selectedSessionId) return;
    const sameSession = runtime.session_id === selectedSessionId;
    const sameIdentity = selectedSessionSummary?.interaction_mode === 'character'
      ? runtime.interaction_mode === 'character' && runtime.character_id === selectedSessionSummary.character_id
      : runtime.interaction_mode !== 'character';
    if (!sameSession || !sameIdentity) {
      liveCallRuntimeRef.current = null;
      setLiveCallRuntime(null);
    }
  }, [selectedSessionId, selectedSessionSummary?.character_id, selectedSessionSummary?.interaction_mode]);

  // Avatar selection can update the live runtime without changing the chat
  // session or interaction query key. Keep the React-owned runtime in sync
  // with the bridge so the visible Live Voice controls and fullscreen surface
  // switch rigs immediately instead of retaining the previous model.
  useEffect(() => {
    const syncSelectedAvatar = (event: Event): void => {
      const runtime = (event as CustomEvent<CharacterLiveCallRuntime | null>).detail;
      if (!runtime || runtime.session_id !== selectedSessionId) return;
      liveCallRuntimeRef.current = runtime;
      setLiveCallRuntime(runtime);
    };
    window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, syncSelectedAvatar);
    return () => window.removeEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, syncSelectedAvatar);
  }, [selectedSessionId]);

  return { liveCallRuntime, setLiveCallRuntime, liveCallRuntimeRef };
}
