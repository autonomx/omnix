/** Pause, Resume and Stop for the podcast run in progress (owner request 2026-11-24). */
export function PodcastRunControls({ paused, stopping, onPause, onResume, onStop }: {
  paused: boolean;
  stopping: boolean;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}) {
  return (
    <div className="podcast-run-controls" role="group" aria-label="Podcast run controls">
      {paused
        ? <button className="ghost-button compact" type="button" disabled={stopping} onClick={onResume}>Resume</button>
        : <button className="ghost-button compact" type="button" disabled={stopping} onClick={onPause}>Pause</button>}
      <button className="ghost-button compact danger" type="button" disabled={stopping} onClick={onStop}>{stopping ? 'Stopping...' : 'Stop'}</button>
      <small>{paused ? 'Paused. The script and preview keep being made; Resume plays on from here.' : 'Stop ends the run: nothing more is generated, the final render included.'}</small>
    </div>
  );
}
