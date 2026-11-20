import { useEffect, useState } from 'react';

import { BLINK_GAP_MAX_MS, BLINK_GAP_MIN_MS, BLINK_MS } from './compositor';
import type { MemberIdleLoop } from './memberIdleLoops';

/**
 * A group call's member who is not speaking (companion 5.5): its portrait's idle loop, frame by frame, with a blink
 * now and then (the loop frame's eyes-shut twin). The speaker's face is the live portrait's canvas instead.
 */
export function PortraitIdleLoop({ loop, label }: { loop: MemberIdleLoop; label: string }) {
  const [index, setIndex] = useState(0);
  const [blinking, setBlinking] = useState(false);

  useEffect(() => {
    setIndex(0);
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % loop.idle.length), loop.frameMs);
    return () => window.clearInterval(timer);
  }, [loop]);

  useEffect(() => {
    if (!loop.blink.length) return undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const next = (shut: boolean) => {
      setBlinking(shut);
      const wait = shut ? BLINK_MS : BLINK_GAP_MIN_MS + Math.random() * (BLINK_GAP_MAX_MS - BLINK_GAP_MIN_MS);
      timer = setTimeout(() => next(!shut), wait);
    };
    next(false);
    return () => clearTimeout(timer);
  }, [loop]);

  const frame = (blinking ? loop.blink[index] : undefined) ?? loop.idle[index % loop.idle.length];
  return <img src={frame} alt={label} data-portrait-idle="true" />;
}
