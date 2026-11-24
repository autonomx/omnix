import { describe, expect, it } from 'vitest';
import { lineAt, stitchedTimeline, timelineFrom } from './podcastTimeline';

describe('podcast timeline', () => {
  it('reads a render timeline as sorted line starts and drops malformed entries', () => {
    expect(timelineFrom([
      { segment: 1, start: 4, end: 9 },
      { segment: 0, start: 1.5, end: 4 },
      { segment: 'x', start: 2 },
      { segment: 2, start: -1 },
      null,
    ])).toEqual([{ line: 0, start: 1.5 }, { line: 1, start: 4 }]);
    expect(timelineFrom(undefined)).toEqual([]);
  });

  it('starts each stitched line where the ones before it end', () => {
    expect(stitchedTimeline([0, 1, 3], [2, 3.5, 1])).toEqual([{ line: 0, start: 0 }, { line: 1, start: 2 }, { line: 3, start: 5.5 }]);
  });

  it('finds the line playing: none before the first, then the last started', () => {
    const timeline = [{ line: 0, start: 2 }, { line: 1, start: 5 }];
    expect(lineAt(timeline, 1)).toBeNull();
    expect(lineAt(timeline, 2)).toBe(0);
    expect(lineAt(timeline, 4.9)).toBe(0);
    expect(lineAt(timeline, 60)).toBe(1);
    expect(lineAt(undefined, 3)).toBeNull();
  });
});
