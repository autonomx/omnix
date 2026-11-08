import { setLiveVoiceMuted, useLiveCallPresentation } from '../workspace';

/**
 * The call's mute button, as in a call app: muted, the call hears silence until it is pressed again. It shows only
 * when the capture controller owns the microphone, and works while a call is running.
 */
export function LiveMuteButton({ className }: { className?: string }) {
  const { captureOwned, captureActive, micMuted } = useLiveCallPresentation();
  if (!captureOwned) return null;
  const classes = [className, micMuted ? 'live-mute-button muted' : 'live-mute-button'].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={classes}
      aria-pressed={micMuted}
      aria-label={micMuted ? 'Unmute microphone' : 'Mute microphone'}
      title={micMuted ? 'Unmute microphone' : 'Mute microphone'}
      disabled={!captureActive}
      onClick={() => setLiveVoiceMuted(!micMuted)}
    >
      {micMuted ? 'Unmute' : 'Mute'}
    </button>
  );
}
