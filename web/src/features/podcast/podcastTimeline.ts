/**
 * Where each script line plays in the audio, so the transcript can follow along (owner request 2026-11-24). A
 * stitched preview knows it from the length of each line's audio; a final render reports it (`timeline` on the
 * output, from `voice/jobs.py`: each line's start in the file, after the opening sting).
 */
export type LineStart = { line: number; start: number };

/** A final render's `timeline` (`[{segment, start, end}]`) as line starts; empty when absent or malformed. */
export function timelineFrom(raw: unknown): LineStart[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    const line = Number(entry?.segment);
    const start = Number(entry?.start);
    return Number.isInteger(line) && line >= 0 && Number.isFinite(start) && start >= 0 ? [{ line, start }] : [];
  }).sort((left, right) => left.start - right.start);
}

/** Line starts for audio joined end to end: each line begins where the ones before it end. */
export function stitchedTimeline(lines: number[], durations: number[]): LineStart[] {
  let start = 0;
  return lines.map((line, index) => {
    const entry = { line, start };
    start += Math.max(0, durations[index] ?? 0);
    return entry;
  });
}

/** The line playing at `seconds`: the last one started; none before the first (the opening sting) or without a timeline. */
export function lineAt(timeline: LineStart[] | undefined, seconds: number): number | null {
  let playing: number | null = null;
  for (const entry of timeline ?? []) {
    if (entry.start > seconds) break;
    playing = entry.line;
  }
  return playing;
}
