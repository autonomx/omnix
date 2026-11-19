import { setLiveCallQuiet, useLiveCallPresentation } from '../workspace';

/**
 * Asks the companion to keep quiet for this call: it starts nothing social of its own, while it still answers and
 * still reports the tasks the person asked for. It shows beside the mute button and works while a call is running.
 */
export function LiveQuietButton({ className }: { className?: string }) {
  const { captureOwned, captureActive, companionQuiet } = useLiveCallPresentation();
  if (!captureOwned) return null;
  const classes = [className, 'live-mute-button live-quiet-button', companionQuiet ? 'quiet' : '']
    .filter(Boolean)
    .join(' ');
  const label = companionQuiet ? 'Let the companion speak up' : 'Keep the companion quiet this call';
  return (
    <button
      type="button"
      className={classes}
      aria-pressed={companionQuiet}
      aria-label={label}
      title={label}
      disabled={!captureActive}
      onClick={() => setLiveCallQuiet(!companionQuiet)}
    >
      {companionQuiet ? 'Quiet on' : 'Quiet'}
    </button>
  );
}
