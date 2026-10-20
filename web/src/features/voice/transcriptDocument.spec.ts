import { describe, expect, it } from 'vitest';
import {
  activeWord,
  asTranscriptDocument,
  editSegmentText,
  isLowConfidence,
  mergeWithNext,
  renameSpeaker,
  setSegmentSpeaker,
  splitSegment,
  type TranscriptDocument,
} from './transcriptDocument';

function documentOf(): TranscriptDocument {
  return asTranscriptDocument({
    schema: 'omnix-transcript-v1', language: 'en', duration: 6, engine: 'Parakeet-TDT', diarized: true,
    speakers: ['Speaker 1', 'Speaker 2'], text: '', source_asset_id: 'audio:talk',
    segments: [
      { start: 0, end: 2, speaker: 'Speaker 1', text: 'Hello there friend.', words: [
        { start: 0, end: 0.5, word: 'Hello', confidence: 0.9 },
        { start: 0.6, end: 1.0, word: 'there', confidence: 0.4 },
        { start: 1.2, end: 2.0, word: 'friend.', confidence: 0.95 },
      ] },
      { start: 3, end: 4, speaker: 'Speaker 2', text: 'Hi!', words: [{ start: 3, end: 4, word: 'Hi!', confidence: null }] },
    ],
  });
}

describe('transcript edits', () => {
  it('renames a speaker everywhere and merges onto an existing name', () => {
    const renamed = renameSpeaker(documentOf(), 'Speaker 1', 'Ana');
    expect(renamed.speakers).toEqual(['Ana', 'Speaker 2']);
    expect(renameSpeaker(renamed, 'Speaker 2', 'Ana').speakers).toEqual(['Ana']);
    expect(renameSpeaker(renamed, 'Ana', '  ')).toBe(renamed);
  });

  it('splits at a word and merges back', () => {
    const split = splitSegment(documentOf(), 0, 2);
    expect(split.segments.map((segment) => segment.text)).toEqual(['Hello there', 'friend.', 'Hi!']);
    expect(split.segments[0].end).toBe(1.0);
    expect(split.segments[1].start).toBe(1.2);
    const merged = mergeWithNext(split, 0);
    expect(merged.segments.map((segment) => segment.text)).toEqual(['Hello there friend.', 'Hi!']);
    expect(splitSegment(documentOf(), 0, 0)).toEqual(documentOf());
  });

  it('keeps word timing when a re-typed segment has the same word count', () => {
    const fixed = editSegmentText(documentOf(), 0, 'Hello their friend.');
    expect(fixed.segments[0].words.map((word) => word.start)).toEqual([0, 0.6, 1.2]);
    expect(fixed.segments[0].words[1]).toMatchObject({ word: 'their', confidence: null });
    const rewritten = editSegmentText(documentOf(), 0, 'Good morning');
    expect(rewritten.segments[0]).toMatchObject({ text: 'Good morning', words: [], start: 0, end: 2 });
    expect(editSegmentText(documentOf(), 1, '   ').segments).toHaveLength(1);
  });

  it('reassigns a segment, recomputing the speaker list', () => {
    expect(setSegmentSpeaker(documentOf(), 1, 'Speaker 1').speakers).toEqual(['Speaker 1']);
  });

  it('flags low-confidence words and follows playback', () => {
    const doc = documentOf();
    expect(doc.segments[0].words.map(isLowConfidence)).toEqual([false, true, false]);
    expect(isLowConfidence(doc.segments[1].words[0])).toBe(false);
    expect(activeWord(doc, 0.7)).toEqual({ segment: 0, word: 1 });
    expect(activeWord(doc, 2.5)).toEqual({ segment: -1, word: -1 });
  });
});
