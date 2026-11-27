/**
 * Block diffs (ST-6.2, ST-6.3): which paragraphs and spoken lines a change kept, removed and added, so a
 * proposal or a version can be read against the manuscript before the writer accepts or restores it.
 */
import type { StoryBlock } from './api/storyClient';

export type DiffChange = 'same' | 'removed' | 'added';
export type DiffLine = { change: DiffChange; block: StoryBlock };

/** A block as the diff compares it: its kind, its speaker and its text, with spacing ignored. */
function blockKey(block: StoryBlock): string {
  const speaker = block.kind === 'dialogue' ? block.speaker_id?.trim() ?? '' : '';
  return `${block.kind ?? 'narration'}\u0000${speaker}\u0000${block.text.trim().replace(/\s+/g, ' ')}`;
}

/** The blocks with text, in order: an empty block shows nothing and changes nothing. */
export function textBlocks(blocks: readonly StoryBlock[]): StoryBlock[] {
  return blocks.filter((block) => block.text.trim());
}

/** Every page's blocks in order, as one list to compare. */
export function manuscriptBlocks(pages: ReadonlyArray<{ blocks: readonly StoryBlock[] }>): StoryBlock[] {
  return pages.flatMap((page) => textBlocks(page.blocks));
}

/**
 * The longest common run of blocks kept in order, then what was removed from `before` and added in `after`
 * around it. A removed block is listed before the added block that replaced it.
 */
export function diffBlocks(before: readonly StoryBlock[], after: readonly StoryBlock[]): DiffLine[] {
  const left = textBlocks(before);
  const right = textBlocks(after);
  const leftKeys = left.map(blockKey);
  const rightKeys = right.map(blockKey);
  // kept[i][j]: how many blocks left[i:] and right[j:] keep in common.
  const kept = Array.from({ length: left.length + 1 }, () => new Array<number>(right.length + 1).fill(0));
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      kept[i][j] = leftKeys[i] === rightKeys[j] ? kept[i + 1][j + 1] + 1 : Math.max(kept[i + 1][j], kept[i][j + 1]);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && leftKeys[i] === rightKeys[j]) {
      lines.push({ change: 'same', block: right[j] });
      i += 1;
      j += 1;
    } else if (j >= right.length || (i < left.length && kept[i + 1][j] >= kept[i][j + 1])) {
      lines.push({ change: 'removed', block: left[i] });
      i += 1;
    } else {
      lines.push({ change: 'added', block: right[j] });
      j += 1;
    }
  }
  return lines;
}

/** How many blocks a diff removes and adds; nothing changed when both are 0. */
export function diffCounts(lines: readonly DiffLine[]): { removed: number; added: number } {
  return {
    removed: lines.filter((line) => line.change === 'removed').length,
    added: lines.filter((line) => line.change === 'added').length,
  };
}
