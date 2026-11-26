import type { AudiobookWorkspaceModel } from './useAudiobookWorkspace';

/** Find speakers' "No reasoning" box: on by default; unticked, the calls use the reasoning level chosen in Settings. */
export function NoReasoningOption({ ws }: { ws: Pick<AudiobookWorkspaceModel, 'noReasoning' | 'setNoReasoning' | 'reclassificationRunning'> }) {
  return (
    <label className="audiobook-reasoning-option"
      title="Answer every speaker call without reasoning, which is much faster. Untick to use the reasoning level set for your model in Settings.">
      <input type="checkbox" checked={ws.noReasoning} disabled={ws.reclassificationRunning}
        onChange={(event) => ws.setNoReasoning(event.target.checked)} />
      No reasoning (faster)
    </label>
  );
}
