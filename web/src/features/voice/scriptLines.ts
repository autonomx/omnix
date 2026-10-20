/**
 * Voice Studio script grammar, shared with `src/app/platform/voice/script.py`.
 *
 * - `name: text` lines speak as `name` (names are at most 50 characters).
 * - Untagged lines join into one Narrator segment.
 * - `{pause 600ms}` or `{pause 1.5s}` inserts silence before the next segment.
 *   Braces, because Fish S2 Pro reads square brackets as delivery instructions.
 * - Blank lines are ignored.
 *
 * Both parsers run `scriptGrammar.vectors.json`, so a script previews as the
 * segments it renders.
 */
export interface ScriptSpeakerRow {
  name: string;
  count: number;
}

export interface ScriptSegmentRow {
  index: number;
  speaker: string;
  text: string;
  /** Explicit silence before this segment, from a `{pause …}` token (wire field). */
  pause_before_ms?: number;
}

const DEFAULT_UNTAGGED_SPEAKER = 'Narrator';
const MAX_SPEAKER_NAME = 50;
export const MAX_PAUSE_MS = 10_000;
const PAUSE_SOURCE = String.raw`\{\s*pause\s+(\d+(?:\.\d+)?)\s*(ms|s)\s*\}`;

export function parseScriptSpeakers(text: string): ScriptSpeakerRow[] {
  const counts = new Map<string, number>();
  for (const segment of parseScriptSegments(text)) {
    counts.set(segment.speaker, (counts.get(segment.speaker) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([name, count]) => ({ name, count }));
}

function pauseMs(value: string, unit: string): number {
  const amount = Number(value);
  const milliseconds = unit.toLowerCase() === 'ms' ? amount : amount * 1000;
  return Math.min(MAX_PAUSE_MS, Math.max(0, Math.round(milliseconds)));
}

export function parseScriptSegments(text: string): ScriptSegmentRow[] {
  const segments: ScriptSegmentRow[] = [];
  const untagged: string[] = [];
  let pendingPause = 0;

  const emit = (speaker: string, content: string) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const segment: ScriptSegmentRow = { index: segments.length, speaker, text: trimmed };
    if (pendingPause && segments.length) segment.pause_before_ms = pendingPause;
    pendingPause = 0;
    segments.push(segment);
  };
  const flushUntagged = () => {
    if (untagged.length) {
      emit(DEFAULT_UNTAGGED_SPEAKER, untagged.join(' '));
      untagged.length = 0;
    }
  };
  const addPause = (value: string, unit: string) => {
    pendingPause = Math.min(MAX_PAUSE_MS, pendingPause + pauseMs(value, unit));
  };

  for (const rawLine of text.split(/\r?\n|\r/)) {
    let line = rawLine.trim();
    if (!line) continue;
    const leading = new RegExp(`^${PAUSE_SOURCE}`, 'i');
    let match = leading.exec(line);
    while (match) {
      flushUntagged();
      addPause(match[1], match[2]);
      line = line.slice(match[0].length).trim();
      match = leading.exec(line);
    }
    if (!line) continue;
    const tagged = parseTaggedLine(line);
    const speaker = tagged?.speaker ?? null;
    const content = tagged ? tagged.text : line;
    if (speaker !== null) flushUntagged();
    let position = 0;
    for (const inner of content.matchAll(new RegExp(PAUSE_SOURCE, 'gi'))) {
      const part = content.slice(position, inner.index).trim();
      if (speaker === null) {
        if (part) untagged.push(part);
        flushUntagged();
      } else {
        emit(speaker, part);
      }
      addPause(inner[1], inner[2]);
      position = (inner.index ?? 0) + inner[0].length;
    }
    const rest = content.slice(position).trim();
    if (speaker === null) {
      if (rest) untagged.push(rest);
    } else {
      emit(speaker, rest);
    }
  }

  flushUntagged();
  return segments;
}

function parseTaggedLine(line: string): { speaker: string; text: string } | null {
  const colon = line.indexOf(':');
  if (colon <= 0) {
    return null;
  }
  const speaker = line.slice(0, colon).trim();
  const text = line.slice(colon + 1).trim();
  if (!speaker || !text || speaker.length > MAX_SPEAKER_NAME) {
    return null;
  }
  return { speaker, text };
}
