import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useSyncExternalStore } from 'react';
import { characterAvatarClient } from '../characterAvatarClient';
import { useLiveAvatar } from '../liveCharacterAvatarBridge';
import { livePortrait, portraitEnabled, portraitNotice } from './livePortrait';

const STATUS_KEY = ['feature', 'chatbot', 'portrait-model'];
const STATUS_POLL_MS = 15_000;
const LOADING_POLL_MS = 2_000;
const LOAD_GIVE_UP_MS = 180_000; // as long as a call waits for the model

/**
 * Loads a portrait's model ahead of the call (D-9), so its video is there when the call starts. A call still loads it
 * if this was not pressed; the model unloads after an idle while, and the button comes back.
 */
export function LivePortraitLoadControl() {
  const avatarPack = useLiveAvatar().runtime?.avatar_pack;
  const portraitState = useSyncExternalStore(livePortrait.subscribe, livePortrait.getSnapshot, livePortrait.getSnapshot);
  const assetId = avatarPack?.renderer === 'portrait' ? avatarPack.base_asset_id : null;
  const shown = Boolean(assetId) && portraitState.status === 'off' && portraitEnabled();
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
  const load = useMutation({
    mutationFn: async () => {
      const giveUpAt = Date.now() + LOAD_GIVE_UP_MS;
      for (;;) {
        const answer = await characterAvatarClient.loadPortrait(assetId ?? '');
        if (answer.status !== 'loading' || !mounted.current) return answer;
        if (Date.now() >= giveUpAt) return { ...answer, status: 'unavailable' as const, code: 'warming' };
        await new Promise((resolve) => { setTimeout(resolve, LOADING_POLL_MS); });
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: STATUS_KEY }),
  });

  if (!shown || model.data?.status === 'unavailable') return null;
  const ready = model.data?.status === 'ready' && !load.isPending;
  const loading = load.isPending || model.data?.status === 'loading';
  const refused = !ready && !loading && load.data?.status === 'unavailable'
    ? portraitNotice({ status: 'unavailable', fallbackRenderer: 'sprite', reason: load.data.code })
    : null;
  const failed = !ready && !loading && load.isError ? 'The live video could not be loaded.' : null;

  return (
    <div className="assistant-live-portrait-load">
      <button type="button" className="assistant-live-fullscreen-button" disabled={ready || loading} data-model-state={ready ? 'ready' : loading ? 'loading' : 'unloaded'} onClick={() => load.mutate()}>
        {ready ? 'Live video ready' : loading ? 'Loading live video…' : 'Load live video'}
      </button>
      {refused || failed ? <small role="status">{refused ?? failed}</small> : null}
    </div>
  );
}
