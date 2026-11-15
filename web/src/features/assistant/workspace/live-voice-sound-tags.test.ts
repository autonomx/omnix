import { describe, expect, it } from 'vitest';

import { StableClauseAccumulator } from './live-voice-clause-stabilizer';
import { markSoundTags, soundTagName, stripSoundTags, takeSoundMarks } from './live-voice-sound-tags';

describe('live voice sound tags', () => {
  it('names only the tags the voice can play', () => {
    expect(soundTagName(' Hmmm ')).toBe('hmm');
    expect(soundTagName('laughs')).toBe('chuckle');
    expect(soundTagName('Sighs')).toBe('sigh');
    expect(soundTagName('soft pause')).toBeNull();
  });

  it('reads where a tag plays and never leaves it in the words', () => {
    const leading = takeSoundMarks(markSoundTags('[hmm] Let me think.'));
    expect(leading).toMatchObject({ cue: 'hmm', leading: true });
    expect(leading.text.trim()).toBe('Let me think.');
    expect(takeSoundMarks(markSoundTags('Fine. [sigh]'))).toMatchObject({ cue: 'sigh', leading: false });
    expect(stripSoundTags('[chuckle] Sure [grins] thing ]')).toBe('Sure thing');
    expect(stripSoundTags('Right [hmm], so.')).toBe('Right, so.');
    expect(stripSoundTags('No tags here.')).toBe('No tags here.');
  });
});

describe('sound tags in stable clauses', () => {
  const clauses = () => new StableClauseAccumulator({ minimumClauseCharacters: 4 });

  it('gives a clause the tag that opens it, even split across chunks', () => {
    const accumulator = clauses();
    expect(accumulator.append('[', 0)).toEqual([]);
    expect(accumulator.append('hmm] Let me think about that.', 1)).toEqual([
      { text: 'Let me think about that.', reason: 'strong-boundary', cue: 'hmm' },
    ]);
  });

  it('carries a tag after words, or standing alone, to the next clause', () => {
    const accumulator = clauses();
    expect(accumulator.append('That is a long story. [sigh] ', 0)).toEqual([
      { text: 'That is a long story.', reason: 'strong-boundary' },
    ]);
    expect(accumulator.append('But here it is.', 1)).toEqual([
      { text: 'But here it is.', reason: 'strong-boundary', cue: 'sigh' },
    ]);
    const midSentence = clauses();
    expect(midSentence.append('Oh well [chuckle] that happens.', 0)).toEqual([
      { text: 'Oh well that happens.', reason: 'strong-boundary' },
    ]);
    expect(midSentence.flush()).toEqual([{ text: '', reason: 'stream-end', cue: 'amused_exhale' }]);
  });

  it('keeps a tag at the end of the reply as a cue-only clause', () => {
    const accumulator = clauses();
    expect(accumulator.append('We made it. [laughs]', 0)).toEqual([
      { text: 'We made it.', reason: 'strong-boundary' },
    ]);
    expect(accumulator.flush()).toEqual([{ text: '', reason: 'stream-end', cue: 'amused_exhale' }]);
  });

  it('never speaks stage directions', () => {
    const accumulator = clauses();
    expect([...accumulator.append('[softly] I know. ', 0), ...accumulator.flush()]).toEqual([
      { text: 'I know.', reason: 'strong-boundary' },
    ]);
  });
});
