import { useEffect, useRef, useState } from 'react';
import { livePortrait } from './livePortrait';

const FRAME_SIZE = 512;

/**
 * The live portrait: the pack's image until the first frame arrives, then the frame for what is heard,
 * drawn on each animation frame. Between frames (a silence, a cue, a late frame) the last one stays up.
 */
export function LivePortraitCanvas({ imageUrl, label }: { imageUrl: string; label: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    const context = canvasRef.current?.getContext('2d');
    if (!context) return undefined;
    let handle = 0;
    let last: ImageBitmap | null = null;
    const draw = () => {
      const frame = livePortrait.currentFrame();
      if (frame && frame !== last) {
        context.drawImage(frame, 0, 0, FRAME_SIZE, FRAME_SIZE);
        last = frame;
        setDrawn(true);
      }
      handle = requestAnimationFrame(draw);
    };
    handle = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(handle);
  }, []);

  return (
    <>
      {drawn ? null : <img src={imageUrl} alt={label} />}
      <canvas ref={canvasRef} width={FRAME_SIZE} height={FRAME_SIZE} aria-label={label} hidden={!drawn} />
    </>
  );
}
