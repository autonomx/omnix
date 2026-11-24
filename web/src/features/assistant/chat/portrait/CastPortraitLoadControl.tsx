import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { characterAvatarClient } from '../characterAvatarClient';
import { isPortraitPack, type StageCharacter } from './CharacterStage';
import { portraitEnabled, portraitNotice } from './livePortrait';
import { LiveVideoLoadProgress, useLoadPlan } from './LiveVideoLoadProgress';
import { PORTRAIT_MODEL_STATUS_KEY } from './LivePortraitLoadControl';
import { planLoad, stepId } from './loadProgress';
import { loadMemberLoop, packRevision, resetMemberLoops, useKnownMemberLoops } from './memberIdleLoops';
// The load bar's styles live with the call's load control.
import '../liveCharacterAvatarBridge.css';

const STATUS_POLL_MS = 15_000;
const LOADING_POLL_MS = 2_000;
const LOAD_GIVE_UP_MS = 180_000; // as long as a call waits for the model

type LoadAnswer = Awaited<ReturnType<typeof characterAvatarClient.loadPortrait>>;

/**
 * "Load live avatars" for a podcast's cast (owner request, 2026-11-23), as "Load live video" is for a call: it loads
 * the portrait model and prepares each cast member's face, its idle loop rendered, so the cast's tiles idle live and
 * the first line has no load to wait for. `runKey` is the stage's: the run that speaks the podcast uses the same one,
 * so the loops kept here are the run's. Pressed again once ready, it unloads the model; the tiles are pictures again.
 * Disabled while the podcast is generating (the service refuses an unload while a face streams).
 */
export function CastPortraitLoadControl({ runKey, members, disabled = false }: {
  runKey: string;
  members: readonly StageCharacter[];
  disabled?: boolean;
}) {
  const faces = members.filter((member) => isPortraitPack(member.pack))
    .map((member) => ({ id: member.id, name: member.name, assetId: member.pack?.base_asset_id ?? '', revision: packRevision(member.pack) }));
  const shown = faces.length > 0 && portraitEnabled();
  const known = useKnownMemberLoops(faces);
  const queryClient = useQueryClient();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const model = useQuery({
    queryKey: PORTRAIT_MODEL_STATUS_KEY,
    queryFn: () => characterAvatarClient.portraitModelStatus(),
    enabled: shown,
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'loading' ? LOADING_POLL_MS : STATUS_POLL_MS),
  });
  const { plan, setPlan, advance, endPlan } = useLoadPlan();

  const load = useMutation({
    mutationFn: async (): Promise<LoadAnswer> => {
      const giveUpAt = Date.now() + LOAD_GIVE_UP_MS;
      setPlan(planLoad([
        ...(model.data?.status === 'ready' ? [] : [{ id: stepId('model'), kind: 'model' as const, name: '' }]),
        ...faces.map((face) => ({ id: stepId('guest', face.id), kind: 'guest' as const, name: face.name })),
      ], Date.now()));
      let answer: LoadAnswer = { status: 'ready', code: '', message: '' };
      for (const face of faces) {
        if (!mounted.current) break;
        answer = await characterAvatarClient.loadPortrait(face.assetId);
        while (answer.status === 'loading' && mounted.current) {
          if (Date.now() >= giveUpAt) return { ...answer, status: 'unavailable', code: 'warming' };
          await new Promise((resolve) => { setTimeout(resolve, LOADING_POLL_MS); });
          const status = await characterAvatarClient.portraitModelStatus().catch(() => null);
          if (status?.status === 'loading') continue;
          if (status?.status === 'ready') advance(stepId('model'));
          // Asked again once the model is up: that ask prepares the face and renders its idle loop.
          answer = await characterAvatarClient.loadPortrait(face.assetId);
        }
        if (answer.status !== 'ready') return answer;
        advance(stepId('guest', face.id));
        await loadMemberLoop(runKey, face.id, null, face.revision, { again: true, outsideChat: true });
      }
      return answer;
    },
    onSettled: () => {
      endPlan();
      void queryClient.invalidateQueries({ queryKey: PORTRAIT_MODEL_STATUS_KEY });
    },
  });
  const unload = useMutation({
    mutationFn: () => characterAvatarClient.unloadPortrait(),
    onSuccess: (answer) => {
      if (!answer.ok) return;
      resetMemberLoops();
      load.reset();
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: PORTRAIT_MODEL_STATUS_KEY }),
  });

  if (!shown || model.data?.status === 'unavailable') return null;
  const modelReady = model.data?.status === 'ready';
  // Ready once every face is prepared; a loop the gateway did not hand back is not a failed load (the member's own
  // turn brings it), so the button can still unload.
  const ready = modelReady && !load.isPending && (known === faces.length || load.data?.status === 'ready');
  const loading = load.isPending || model.data?.status === 'loading';
  const unloading = unload.isPending;
  const refused = !ready && !loading && load.data?.status === 'unavailable'
    ? portraitNotice({ status: 'unavailable', fallbackRenderer: 'sprite', reason: load.data.code })
    : null;
  const failed = !ready && !loading && load.isError ? 'The live avatars could not be loaded.' : null;
  const kept = ready && !unloading && (unload.isError || unload.data?.ok === false)
    ? unload.data?.message || 'The live avatars could not be unloaded.'
    : null;
  const partial = ready && !unloading && known < faces.length
    ? 'Some idle loops are not ready yet; those tiles show a picture until the member speaks.'
    : null;
  const notice = refused ?? failed ?? kept ?? partial;

  return (
    <div className="assistant-live-portrait-load character-stage-load">
      <button
        type="button"
        className="ghost-button compact"
        disabled={disabled || loading || unloading}
        aria-pressed={ready}
        title={ready ? 'Unload live avatars' : undefined}
        data-model-state={unloading ? 'unloading' : ready ? 'ready' : loading ? 'loading' : 'unloaded'}
        onClick={() => {
          if (ready) {
            unload.mutate();
            return;
          }
          unload.reset();
          load.mutate();
        }}
      >
        {unloading ? 'Unloading live avatars…' : ready ? 'Live avatars ready' : loading ? 'Loading live avatars…' : 'Load live avatars'}
      </button>
      {loading && !ready ? <LiveVideoLoadProgress plan={load.isPending ? plan : null} /> : null}
      {notice ? <small role="status">{notice}</small> : null}
    </div>
  );
}
