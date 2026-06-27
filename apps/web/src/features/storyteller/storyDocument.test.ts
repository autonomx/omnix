import { describe, expect, it } from 'vitest';
import { allStoryBlocks, buildStoryDocumentFromText } from './storyDocument';

function dialogueSpeaker(text: string, fragment: string): string | undefined {
  const document = buildStoryDocumentFromText({ title: 'Barn Mystery', text });
  const block = allStoryBlocks(document).find((candidate) => candidate.kind === 'dialogue' && candidate.text.includes(fragment));
  return block?.kind === 'dialogue' ? block.speakerName : undefined;
}

describe('Storyteller dialogue attribution', () => {
  it('prefers trailing explicit speaker attribution over later paragraph names', () => {
    const text = [
      'Farmer Giles had been losing patience. Clara, his pragmatic wife, leaned against the barn while young Thomas peered through a knothole.',
      '"Or perhaps it\'s just old Silas settling in for his evening nap," Clara suggested, though her voice lacked conviction. Barnaby, perched on Giles’ shoulder, twitched an ear.',
      'Barnaby watched Clara and Thomas from the rafters. Giles muttered to himself while Clara frowned.',
    ].join('\n\n');

    expect(dialogueSpeaker(text, 'old Silas')).toBe('Clara');
  });

  it('resolves pronoun attribution to the nearest preceding character', () => {
    const text = [
      'Farmer Giles had been losing patience. Clara, his pragmatic wife, leaned against the barn while young Thomas peered through a knothole.',
      '"It sounds like something heavy is dragging itself across the hay bales," he whispered, kicking at a loose stone near the foundation.',
      'Barnaby watched Clara and Thomas from the rafters. Giles muttered to himself while Clara frowned.',
    ].join('\n\n');

    expect(dialogueSpeaker(text, 'hay bales')).toBe('Thomas');
  });

  it('uses later explicit quote attribution for short exclamations', () => {
    const text = [
      'Giles stared at the barn door while Barnaby, Clara, and Thomas clustered behind him.',
      '"What in tarnation is that?" Giles boomed, dropping his pitchfork.',
      'Barnaby watched Clara and Thomas from the rafters. Giles muttered to himself while Clara frowned.',
    ].join('\n\n');

    expect(dialogueSpeaker(text, 'tarnation')).toBe('Giles');
  });
});
