import { useEffect, useRef } from 'react';

import { dismissCameraShareError, toggleCameraShare, useCameraShare } from '../workspace';
import { LiveShowButton } from './LiveShowButton';
import './CameraShare.css';

/**
 * The shared front camera's toggle (camera share, 2026-11-21): in the composer beside Desktop, and in the call's
 * controls. Only this press opens the camera; it stays shared until pressed again.
 */
export function CameraShareButton({ variant = 'composer' }: { variant?: 'composer' | 'call' }) {
  const share = useCameraShare();
  const sharing = share.phase === 'on' || share.phase === 'opening';
  const label = sharing ? 'Stop sharing the camera' : 'Share the camera';
  const button = variant === 'call' ? (
    <button
      type="button"
      className={`live-mute-button live-camera-button${sharing ? ' on' : ''}`}
      aria-label={label}
      aria-pressed={sharing}
      title={label}
      onClick={() => void toggleCameraShare()}
    >
      {share.phase === 'opening' ? 'Opening…' : sharing ? 'Camera on' : 'Camera'}
    </button>
  ) : (
    <button
      type="button"
      className={`assistant-context-desktop-inline assistant-context-desktop${sharing ? ' active' : ''}`}
      data-omnix-camera-action="true"
      aria-label={label}
      aria-pressed={sharing}
      onClick={() => void toggleCameraShare()}
    >
      <span>Camera</span><strong>{share.phase === 'opening' ? 'Opening' : sharing ? 'Sharing' : 'Off'}</strong>
    </button>
  );
  return (
    <>
      {button}
      {share.phase === 'error' && share.error ? (
        <span className="camera-share-error" role="alert">
          {share.error}
          <button type="button" aria-label="Dismiss camera message" onClick={dismissCameraShareError}>×</button>
        </span>
      ) : null}
    </>
  );
}

/** The call's camera buttons: Show for one picture, Camera to share it (Show steps aside while it is shared). */
export function LiveCallCameraButtons() {
  return (
    <>
      <LiveShowButton />
      <CameraShareButton variant="call" />
    </>
  );
}

/**
 * The person's own view while the camera is shared: a small mirrored tile in the corner of the live avatar's
 * stage, video-call style, so they always see what the assistant may see.
 */
export function CameraSelfView() {
  const share = useCameraShare();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const stream = share.phase === 'on' ? share.stream : null;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    if (stream) void video.play?.()?.catch?.(() => undefined);
  }, [stream]);

  if (!stream) return null;
  return (
    <div className="camera-self-view" data-omnix-camera-self-view="true">
      <video ref={videoRef} aria-label="Your shared camera" autoPlay muted playsInline />
      <span className="camera-self-view-badge">Camera on</span>
    </div>
  );
}
