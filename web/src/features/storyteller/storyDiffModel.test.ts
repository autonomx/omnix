import { describe, expect, it } from 'vitest';
import type { StoryBlock } from './api/storyClient';
import { diffBlocks, diffCounts, manuscriptBlocks } from './storyDiffModel';

const said = (text: string, speaker: string | null = null): StoryBlock => ({ kind: 'dialogue', text, speaker_id: speaker, attribution: null });
const told = (text: string): StoryBlock => ({ kind: 'narration', text, speaker_id: null, attribution: null });
const changes = (before: StoryBlock[], after: StoryBlock[]) => diffBlocks(before, after).map((line) => `${line.change}:${line.block.text}`);

describe('storyDiffModel', () => {
  it('keeps the blocks both sides share and lists a removed block before the one that replaced it', () => {
    expect(changes([told('A'), told('B'), told('C')], [told('A'), told('B2'), told('C')])).toEqual(['same:A', 'removed:B', 'added:B2', 'same:C']);
  });

  it('ignores spacing and empty blocks, but not a change of speaker or kind', () => {
    expect(changes([told('One  line.'), told('  ')], [told('One line. ')])).toEqual(['same:One line. ']);
    expect(diffCounts(diffBlocks([said('Hello', 'mira')], [said('Hello', 'tomas')]))).toEqual({ removed: 1, added: 1 });
    expect(diffCounts(diffBlocks([said('Hello')], [told('Hello')]))).toEqual({ removed: 1, added: 1 });
  });

  it('reads inserted and deleted paragraphs, and counts nothing for the same story', () => {
    expect(changes([told('A'), told('C')], [told('A'), told('B'), told('C')])).toEqual(['same:A', 'added:B', 'same:C']);
    expect(changes([told('A'), told('B')], [told('B')])).toEqual(['removed:A', 'same:B']);
    const pages = [{ blocks: [told('A'), told('')] }, { blocks: [said('B', 'mira')] }];
    expect(manuscriptBlocks(pages).map((block) => block.text)).toEqual(['A', 'B']);
    expect(diffCounts(diffBlocks(manuscriptBlocks(pages), manuscriptBlocks(pages)))).toEqual({ removed: 0, added: 0 });
  });
});
