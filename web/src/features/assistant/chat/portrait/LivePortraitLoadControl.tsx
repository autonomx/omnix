import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { characterAvatarClient } from '../characterAvatarClient';
import { useLiveConversationSelector } from '../../workspace';
import { callSceneGuests, useCallScene } from '../../workspace/live-call-scene';
import { useLiveAvatar } from '../liveCharacterAvatarBridge';
import {
  cancelLiveVideo, livePortrait, liveVideoRequested, portraitEnabled, portraitNotice, requestLiveVideo,
  subscribeLiveVideo,
} from './livePortrait';
import { LiveVideoLoadProgress, useLoadPlan } from './LiveVideoLoadProgress';
import { planLoad, stepId } from './loadProgress';
import {
  claimGuestRender, guestRenderPending, loadMemberLoop, packRevision, resetMemberLoops, useMemberLoop,
} from './memberIdleLoops';

/** The portrait model's status query, shared by every load button on screen. */
export const PORTRAIT_MODEL_STATUS_KEY = ['feature', 'chatbot', 'portrait-model'];
const STATUS_KEY = PORTRAIT_MODEL_STATUS_KEY;
const STATUS_POLL_MS = 15_000;
const LOADING_POLL_MS = 2_000;
const LOAD_GIVE_UP_MS = 180_000; // as long as a call waits for the model

/**
 * Turns live video on for this chat and loads the portrait's model (D-9), so its video is there when the call starts.
 * A call without it is voice only: the picture stays still (owner, 2026-11-22). Pressed during a call, the video
 * starts with the next reply. The model unloads after an idle while, and the button comes back. Loading renders the
 * face's idle loop, and the stage plays it before the call (owner request, 2026-11-21): the loop is fetched once the
 * model is ready and video is on, and the button stays pressable while this face's loop is not known. Guests on the
 * call get theirs rendered too, one at a time and never during a call (owner report, 2026-11-22: an invited guest
 * stayed a still picture), so every portrait member idles live from the start. Pressed again once ready, it unloads
 * the model and turns video off for this chat, so the faces are still pictures again (owner request, 2026-11-22); the
 * service refuses while a call streams video. While it loads, a bar under it shows the step under way and about how
 * long is left (`loadProgress.ts`).
 */
export function LivePortraitLoadControl() {
  const runtime = useLiveAvatar().runtime;
  const avatarPack = runtime?.avatar_pack;
  const portraitState = useSyncExternalStore(livePortrait.subscribe, livePortrait.getSnapshot, livePortrait.getSnapshot);
  const assetId = avatarPack?.renderer === 'portrait' ? avatarPack.base_asset_id : null;
  const shown = Boolean(assetId) && portraitState.status === 'off' && portraitEnabled();
  const chatSessionId = useLiveConversationSelector((state) => state.sessionId);
  const requested = useSyncExternalStore(subscribeLiveVideo, () => liveVideoRequested(chatSessionId));
  const characterId = assetId ? avatarPack?.character_id ?? null : null;
  const revision = packRevision(avatarPack);
  const idleLoop = useMemberLoop(characterId, revision);
  const queryClient = useQueryClient();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const model = useQuery({
    queryKey: STATUS_KEY,
    queryFn: () => characterAvatarClient.portraitModelStatus(),
    enabled: shown,
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'loading' ? LOADING_POLL_MS : STATUS_POLL_MS),
  });
  // The call's portrait guests: each one's picture, rendered into its loop once the model is ready.
  const scene = useCallScene();
  const connected = useLiveConversationSelector((state) => state.conversation.connection === 'connected');
  const sceneGuests = chatSessionId && scene.sessionId === chatSessionId ? callSceneGuests(scene) : [];
  const guestRuntime = scene.guests ?? runtime?.scene_guests ?? [];
  const guestPortraits = sceneGuests
    .map((guest) => guestRuntime.find((entry) => entry.character_id === guest.character_id)?.avatar_pack)
    .filter((guestPack) => guestPack?.renderer === 'portrait' && guestPack.base_asset_id)
    .map((guestPack) => [guestPack?.character_id, guestPack?.base_asset_id, packRevision(guestPack)].join('\n'))
    .join('\t');
  const guestName = (guestId: string) => sceneGuests.find((guest) => guest.character_id === guestId)?.display_name ?? '';
  const guestStep = (guestId: string) => ({ id: stepId('guest', guestId), kind: 'guest' as const, name: guestName(guestId) });
  // Guests the load will go on to prepare: never during a call (see the guests' effect below).
  const pendingGuests = () => (chatSessionId && !connected && guestPortraits ? guestPortraits.split('\t') : [])
    .map((entry) => entry.split('\n'))
    .filter(([guestId, , guestRevision]) => guestRenderPending(chatSessionId ?? '', guestId, guestRevision));
  const [preparingGuests, setPreparingGuests] = useState(0);

  const { plan, planRef, setPlan, advance, endPlan } = useLoadPlan();

  const load = useMutation({
    mutationFn: async () => {
      const giveUpAt = Date.now() + LOAD_GIVE_UP_MS;
      setPlan(planLoad([
        ...(model.data?.status === 'ready' ? [] : [{ id: stepId('model'), kind: 'model' as const, name: '' }]),
        { id: stepId('face'), kind: 'face', name: runtime?.display_name ?? '' },
        ...pendingGuests().map(([guestId]) => guestStep(guestId)),
      ], Date.now()));
      let answer = await characterAvatarClient.loadPortrait(assetId ?? '');
      while (answer.status === 'loading' && mounted.current) {
        if (Date.now() >= giveUpAt) return { ...answer, status: 'unavailable' as const, code: 'warming' };
        await new Promise((resolve) => { setTimeout(resolve, LOADING_POLL_MS); });
        // Asked again once the model is up: that ask prepares the face and renders its idle loop.
        const status = await characterAvatarClient.portraitModelStatus().catch(() => null);
        if (status?.status === 'loading') continue;
        if (status?.status === 'ready') advance(stepId('face'));
        answer = await characterAvatarClient.loadPortrait(assetId ?? '');
      }
      // The loop was rendered with the model: ask for it again, past an earlier refusal.
      if (answer.status === 'ready' && chatSessionId && characterId) {
        await loadMemberLoop(chatSessionId, characterId, null, revision, { again: true });
      }
      return answer;
    },
    onSettled: (answer) => {
      void queryClient.invalidateQueries({ queryKey: STATUS_KEY });
      // With guests still to prepare, their effect carries the plan on; otherwise the load is over.
      if (answer?.status !== 'ready' || pendingGuests().length === 0) endPlan();
    },
  });
  const unload = useMutation({
    mutationFn: () => characterAvatarClient.unloadPortrait(),
    onSuccess: (answer) => {
      if (!answer.ok) return;
      if (chatSessionId) cancelLiveVideo(chatSessionId);
      resetMemberLoops();
      load.reset();
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: STATUS_KEY }),
  });
  const modelReady = shown && model.data?.status === 'ready';
  useEffect(() => {
    if (requested && modelReady && chatSessionId && characterId && !idleLoop) {
      void loadMemberLoop(chatSessionId, characterId, null, revision);
    }
  }, [requested, modelReady, chatSessionId, characterId, revision, idleLoop]);

  useEffect(() => {
    // Never during a call: a loop rendered then would hold the GPU ahead of the speaker's frames.
    if (!requested || !modelReady || load.isPending || connected || !chatSessionId || !guestPortraits) return;
    const todo = guestPortraits.split('\t').map((entry) => entry.split('\n'))
      .filter(([guestId, , guestRevision]) => claimGuestRender(chatSessionId, guestId, guestRevision));
    if (todo.length === 0) return;
    setPreparingGuests((count) => count + 1);
    // Carried on from the press's plan, or a plan of their own (a guest invited after the load).
    const carried = planRef.current;
    if (!carried || !todo.every(([guestId]) => carried.steps.some((step) => step.id === stepId('guest', guestId)))) {
      setPlan(planLoad(todo.map(([guestId]) => guestStep(guestId)), Date.now()));
    }
    void (async () => {
      for (const [guestId, guestAsset, guestRevision] of todo) {
        advance(stepId('guest', guestId));
        try {
          const answer = await characterAvatarClient.loadPortrait(guestAsset);
          if (answer.status === 'ready') await loadMemberLoop(chatSessionId, guestId, guestId, guestRevision, { again: true });
        } catch {
          // The guest keeps its picture until its own turn brings its loop.
        }
      }
    })().finally(() => {
      endPlan();
      if (mounted.current) setPreparingGuests((count) => count - 1);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the plan helpers read refs and this render's guests
  }, [requested, modelReady, load.isPending, connected, chatSessionId, guestPortraits]);

  if (!shown || model.data?.status === 'unavailable') return null;
  const ready = requested && modelReady && !load.isPending && preparingGuests === 0 && Boolean(idleLoop);
  const loading = load.isPending || preparingGuests > 0 || model.data?.status === 'loading';
  const unloading = unload.isPending;
  const refused = !ready && !loading && load.data?.status === 'unavailable'
    ? portraitNotice({ status: 'unavailable', fallbackRenderer: 'sprite', reason: load.data.code })
    : null;
  const failed = !ready && !loading && load.isError ? 'The live video could not be loaded.' : null;
  const kept = ready && !unloading && (unload.isError || unload.data?.ok === false)
    ? unload.data?.message || 'The live video could not be unloaded.'
    : null;
  const notice = refused ?? failed ?? kept;

  return (
    <div className="assistant-live-portrait-load">
      <button
        type="button"
        className="assistant-live-fullscreen-button"
        disabled={loading || unloading}
        aria-pressed={ready}
        title={ready ? 'Unload live video' : undefined}
        data-model-state={unloading ? 'unloading' : ready ? 'ready' : loading ? 'loading' : 'unloaded'}
        onClick={() => {
          if (ready) {
            unload.mutate();
            return;
          }
          unload.reset();
          if (chatSessionId) requestLiveVideo(chatSessionId);
          load.mutate();
        }}
      >
        {unloading ? 'Unloading live video…' : ready ? 'Live video ready' : loading ? 'Loading live video…' : 'Load live video'}
      </button>
      {loading && !ready ? <LiveVideoLoadProgress plan={load.isPending || preparingGuests > 0 ? plan : null} /> : null}
      {notice ? <small role="status">{notice}</small> : null}
    </div>
  );
}
