import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { loadSettingsProfile, saveAssistantSettings, type LivePortraitEngine } from '../../../settings';
import { resetMemberLoops } from './memberIdleLoops';

const ENGINE_KEY = ['feature', 'chatbot', 'live-portrait-engine'];
// LivePortraitLoadControl's status of the loaded model.
const PORTRAIT_MODEL_KEY = ['feature', 'chatbot', 'portrait-model'];

const ENGINES: ReadonlyArray<{ id: LivePortraitEngine; label: string; description: string }> = [
  { id: 'float', label: 'FLOAT', description: 'Lighter on the GPU and memory.' },
  { id: 'flashhead-lite', label: 'FlashHead Lite', description: 'Closer lip-sync; about twice the GPU and more memory.' },
];

/**
 * The live portrait engine (Live Chat's Video tab; it was in Settings → Assistant & Chat until 2026-11-21). It is a
 * profile setting the gateway reads when it prepares a portrait, so it is saved at once, and the portrait service
 * loads the chosen engine before the next call.
 */
export function LivePortraitEngineCard() {
  const queryClient = useQueryClient();
  const engine = useQuery({
    queryKey: ENGINE_KEY,
    queryFn: async () => (await loadSettingsProfile()).profile.assistant.livePortraitEngine,
    retry: false,
  });
  const save = useMutation({
    mutationFn: (choice: LivePortraitEngine) => saveAssistantSettings({ livePortraitEngine: choice }),
    onSuccess: (assistant) => {
      queryClient.setQueryData(ENGINE_KEY, assistant.livePortraitEngine);
      // The loaded model and the idle loops it rendered were the other engine's (review 2026-11-22: the video button
      // still said ready and the stage played the old engine's loop).
      void queryClient.invalidateQueries({ queryKey: PORTRAIT_MODEL_KEY });
      resetMemberLoops();
    },
  });
  const current = engine.data;
  const status = save.isError ? 'The engine could not be saved.'
    : engine.isError ? 'Settings are unavailable.'
      : save.isSuccess ? 'Saved. The next call uses this engine.' : null;

  return (
    <section className="live-chat-card" aria-labelledby="live-chat-portrait-engine-heading">
      <header>
        <div>
          <p className="eyebrow">Live video</p>
          <h3 id="live-chat-portrait-engine-heading">Portrait engine</h3>
          <p>Which model animates a portrait character in live calls. Switching reloads the portrait service before the next call.</p>
        </div>
      </header>
      <div role="group" className="live-chat-mode-profile-grid" aria-label="Live portrait engine">
        {ENGINES.map((choice) => (
          <button
            key={choice.id}
            type="button"
            className="live-chat-mode-profile"
            aria-pressed={current === choice.id}
            disabled={current === undefined || save.isPending}
            onClick={() => { if (choice.id !== current) save.mutate(choice.id); }}
          >
            <strong>{choice.label}</strong>
            <span>{choice.description}</span>
          </button>
        ))}
      </div>
      {status ? <p className="live-chat-note" role="status">{status}</p> : null}
    </section>
  );
}
