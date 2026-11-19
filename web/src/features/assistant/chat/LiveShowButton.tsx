import { useEffect, useRef } from 'react';

import {
  closeLiveCallCamera,
  openLiveCallCamera,
  refreshLiveCallCameraAvailability,
  takeLiveCallCameraPicture,
  useLiveCallCamera,
  useLiveCallPresentation,
  useLiveConversationSelector,
} from '../workspace';
import './LiveShowButton.css';

/**
 * Show: one picture from the front camera for the person's next turn (live companion roadmap 4.1). It appears only
 * while a call runs and its vision is configured and allowed. The first press opens the camera with a preview and
 * a visible "Camera on"; the second takes the picture and the camera stops. Only a press opens it: when the call
 * asks to see something (4.3), the button is only shown more prominently.
 */
export function LiveShowButton({ className }: { className?: string }) {
  const { captureOwned, captureActive } = useLiveCallPresentation();
  const sessionId = useLiveConversationSelector((runtime) => runtime.sessionId);
  const camera = useLiveCallCamera();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (captureOwned && captureActive && sessionId) void refreshLiveCallCameraAvailability(sessionId);
  }, [captureOwned, captureActive, sessionId]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = camera.stream;
    if (camera.stream) void video.play?.()?.catch?.(() => undefined);
  }, [camera.stream]);

  if (!captureOwned || !captureActive || !camera.available || camera.availabilitySessionId !== sessionId) return null;

  const previewing = camera.phase === 'preview';
  const requested = camera.requested !== null && (camera.phase === 'off' || camera.phase === 'error');
  const classes = [className, 'live-mute-button live-show-button', requested ? 'requested' : '', previewing ? 'on' : '']
    .filter(Boolean)
    .join(' ');
  const label = previewing ? 'Take the picture'
    : camera.phase === 'attached' ? 'Take another picture'
      : requested ? `Show the companion ${camera.requested}` : 'Show the companion something with your camera';
  const text = previewing ? 'Take picture' : camera.phase === 'opening' ? 'Opening…' : 'Show';

  return (
    <>
      <button
        type="button"
        className={classes}
        aria-label={label}
        title={label}
        disabled={camera.phase === 'opening'}
        onClick={() => {
          if (previewing) {
            if (videoRef.current) takeLiveCallCameraPicture(videoRef.current);
            return;
          }
          void openLiveCallCamera();
        }}
      >
        {text}
      </button>
      {camera.phase === 'opening' || previewing || camera.phase === 'attached' || camera.error ? (
        <div className="live-show-panel" role="group" aria-label="Camera">
          {camera.phase === 'opening' || previewing ? (
            <>
              <span className="live-show-indicator" role="status">Camera on</span>
              <video ref={videoRef} aria-label="Camera preview" autoPlay muted playsInline />
              <button type="button" onClick={closeLiveCallCamera}>Close camera</button>
            </>
          ) : camera.phase === 'attached' ? (
            <>
              <p role="status">Picture ready: it goes with what you say next.</p>
              <button type="button" onClick={closeLiveCallCamera}>Discard picture</button>
            </>
          ) : (
            <>
              <p role="alert">{camera.error}</p>
              <button type="button" onClick={closeLiveCallCamera}>Dismiss</button>
            </>
          )}
        </div>
      ) : null}
    </>
  );
}
