import { describe, expect, it } from 'vitest';
import { narrationBlocks } from './rpgVoices';

describe('narrationBlocks', () => {
  it('speaks a quote inside narration in its speakers voice and the rest in the narrators', () => {
    const text = 'Liora leans close. "Stay near me." The wind rises.';
    const start = text.indexOf('"');
    expect(narrationBlocks(text, [{ speaker_id: 'npc:liora-fen', start, end: start + 15 }])).toEqual([
      { speakerId: 'narrator', text: 'Liora leans close. ' },
      { speakerId: 'npc:liora-fen', text: '"Stay near me."' },
      { speakerId: 'narrator', text: ' The wind rises.' },
    ]);
  });
});
