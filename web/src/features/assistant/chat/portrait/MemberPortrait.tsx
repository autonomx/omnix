import { LivePortraitCanvas } from './LivePortraitCanvas';
import { PortraitIdleLoop } from './PortraitIdleLoop';
import { useMemberLoop } from './memberIdleLoops';

/**
 * One call member's portrait (companion 5.5). The member whose turn the live portrait streams (`live`) is drawn on its
 * canvas, its idle loop showing until the first frame; every other member plays its own idle loop, or shows its
 * picture until a loop is known. A member's face is never drawn from another member's stream.
 */
export function MemberPortrait({ characterId, revision = '', imageUrl, label, live, streaming }: {
  characterId: string | null | undefined;
  /** The member's pack as drawn (`packRevision`): a loop from an older pack is not this face. */
  revision?: string;
  imageUrl: string;
  label: string;
  /** The live portrait is this member's (its turn, or the chat's own character outside a group turn). */
  live: boolean;
  /** Whether the live portrait is streaming (not off): the canvas is keyed by it, so a new call starts clean. */
  streaming: boolean;
}) {
  const loop = useMemberLoop(characterId, revision);
  const idle = loop ? <PortraitIdleLoop loop={loop} label={label} /> : null;
  if (live) {
    return <LivePortraitCanvas key={streaming ? 'call' : 'idle'} imageUrl={imageUrl} label={label} placeholder={idle} />;
  }
  return idle ?? <img src={imageUrl} alt={label} />;
}
