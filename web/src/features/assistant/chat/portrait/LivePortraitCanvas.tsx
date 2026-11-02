import { useEffect, useRef, useState } from 'react';
import type { PortraitPicture } from './compositor';
import { livePortrait } from './livePortrait';

const FRAME_SIZE = 512;

/**
 * The live portrait: the pack's image until there is a frame to show (the idle loop or speech), then on each
 * animation frame what the compositor picks, crossfades included.
 */
export function LivePortraitCanvas({ imageUrl, label }: { imageUrl: string; label: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [drawn, setDrawn] = useState(false);
  const [settledUrl, setSettledUrl] = useState<string | null>(null);

  useEffect(() => {
    const context = canvasRef.current?.getContext('2d');
    if (!context) return undefined;
    let handle = 0;
    let shown: PortraitPicture<ImageBitmap> | null = null;
    const draw = (now: number) => {
      const picture = livePortrait.picture(now);
      const unchanged = shown && !picture.over && !shown.over && picture.under === shown.under;
      if (picture.under && !unchanged && paint(context, picture)) {
        shown = picture;
        setDrawn(true);
      }
      handle = requestAnimationFrame(draw);
    };
    handle = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(handle);
  }, []);

  return (
    <>
      {drawn ? null : <img src={imageUrl} alt={label} onLoad={() => setSettledUrl(imageUrl)} onError={() => setSettledUrl(imageUrl)} />}
      <canvas ref={canvasRef} width={FRAME_SIZE} height={FRAME_SIZE} aria-label={label} hidden={!drawn} />
      {drawn || settledUrl === imageUrl ? null : <AvatarLoadingNotice />}
    </>
  );
}

/** Says the avatar is on its way. It fades in late (the stylesheet), so a quick load shows nothing. */
export function AvatarLoadingNotice() {
  return <p className="assistant-live-portrait-notice is-avatar-loading" role="status">Loading avatar…</p>;
}

/** Draw a picture; false when one of its frames was already released (a cancelled turn's), leaving the canvas. */
function paint(context: CanvasRenderingContext2D, picture: PortraitPicture<ImageBitmap>): boolean {
  try {
    context.globalAlpha = 1;
    if (picture.under) context.drawImage(picture.under, 0, 0, FRAME_SIZE, FRAME_SIZE);
    if (picture.over) {
      context.globalAlpha = picture.alpha;
      context.drawImage(picture.over, 0, 0, FRAME_SIZE, FRAME_SIZE);
    }
    return true;
  } catch {
    return false;
  } finally {
    context.globalAlpha = 1;
  }
}
