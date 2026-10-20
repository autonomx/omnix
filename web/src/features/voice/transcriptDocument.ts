/**
 * The `omnix-transcript-v1` document and the edits the Transcribe tool makes to
 * it. Edits never touch timing they cannot keep: a re-typed segment keeps its
 * word timing only when the word count is unchanged.
 */
export interface TranscriptWord {
  start: number;
  end: number;
  word: string;
  confidence?: number | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  speaker: string;
  text: string;
  words: TranscriptWord[];
}

export interface TranscriptDocument {
  schema: string;
  language: string;
  duration: number;
  engine: string;
  diarized: boolean;
  speakers: string[];
  segments: TranscriptSegment[];
  text: string;
  source_asset_id: string;
}

/** Words the engine was unsure of are highlighted for review. */
export const LOW_CONFIDENCE = 0.6;

export function isLowConfidence(word: TranscriptWord): boolean {
  return typeof word.confidence === 'number' && word.confidence < LOW_CONFIDENCE;
}

export function asTranscriptDocument(value: Record<string, unknown>): TranscriptDocument {
  const segments = Array.isArray(value.segments) ? (value.segments as TranscriptSegment[]) : [];
  return {
    schema: String(value.schema ?? 'omnix-transcript-v1'),
    language: String(value.language ?? 'auto'),
    duration: Number(value.duration ?? 0),
    engine: String(value.engine ?? ''),
    diarized: Boolean(value.diarized),
    speakers: Array.isArray(value.speakers) ? value.speakers.map(String) : [],
    segments: segments.map((segment) => ({ ...segment, words: Array.isArray(segment.words) ? segment.words : [] })),
    text: String(value.text ?? ''),
    source_asset_id: String(value.source_asset_id ?? ''),
  };
}

function withSegments(document: TranscriptDocument, segments: TranscriptSegment[]): TranscriptDocument {
  const speakers: string[] = [];
  for (const segment of segments) if (!speakers.includes(segment.speaker)) speakers.push(segment.speaker);
  return { ...document, segments, speakers, text: segments.map((segment) => segment.text).join(' ').trim() };
}

function joined(words: TranscriptWord[]): string {
  return words.map((word) => word.word).join(' ').trim();
}

/** Rename a speaker everywhere; renaming onto an existing name merges the two. */
export function renameSpeaker(document: TranscriptDocument, from: string, to: string): TranscriptDocument {
  const name = to.trim();
  if (!name || name === from) return document;
  return withSegments(document, document.segments.map((segment) => (segment.speaker === from ? { ...segment, speaker: name } : segment)));
}

export function setSegmentSpeaker(document: TranscriptDocument, index: number, speaker: string): TranscriptDocument {
  return withSegments(document, document.segments.map((segment, position) => (position === index ? { ...segment, speaker } : segment)));
}

/** Split a segment so the word at `wordIndex` starts a new segment (same speaker). */
export function splitSegment(document: TranscriptDocument, index: number, wordIndex: number): TranscriptDocument {
  const segment = document.segments[index];
  if (!segment || wordIndex <= 0 || wordIndex >= segment.words.length) return document;
  const before = segment.words.slice(0, wordIndex);
  const after = segment.words.slice(wordIndex);
  const first = { ...segment, words: before, text: joined(before), end: before[before.length - 1].end };
  const second = { ...segment, words: after, text: joined(after), start: after[0].start };
  return withSegments(document, [...document.segments.slice(0, index), first, second, ...document.segments.slice(index + 1)]);
}

/** Merge a segment with the next one; the merged segment keeps the first one's speaker. */
export function mergeWithNext(document: TranscriptDocument, index: number): TranscriptDocument {
  const first = document.segments[index];
  const second = document.segments[index + 1];
  if (!first || !second) return document;
  const words = [...first.words, ...second.words];
  const merged = {
    ...first,
    end: Math.max(first.end, second.end),
    words,
    text: words.length ? joined(words) : `${first.text} ${second.text}`.trim(),
  };
  return withSegments(document, [...document.segments.slice(0, index), merged, ...document.segments.slice(index + 2)]);
}

/**
 * Replace a segment's text. With the same number of words each word keeps its
 * timing; otherwise the words are dropped and the segment's span is kept
 * (subtitles then spread its text evenly).
 */
export function editSegmentText(document: TranscriptDocument, index: number, text: string): TranscriptDocument {
  const segment = document.segments[index];
  if (!segment) return document;
  const tokens = text.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return withSegments(document, document.segments.filter((_, position) => position !== index));
  const words = tokens.length === segment.words.length
    ? segment.words.map((word, position) => (word.word === tokens[position] ? word : { ...word, word: tokens[position], confidence: null }))
    : [];
  return withSegments(document, document.segments.map((entry, position) => (position === index ? { ...entry, words, text: tokens.join(' ') } : entry)));
}

/** The segment and word being spoken at `time`, for following playback. */
export function activeWord(document: TranscriptDocument, time: number): { segment: number; word: number } {
  const segment = document.segments.findIndex((entry) => time >= entry.start && time <= entry.end);
  if (segment < 0) return { segment: -1, word: -1 };
  const word = document.segments[segment].words.findIndex((entry) => time >= entry.start && time <= entry.end);
  return { segment, word };
}

export function formatClock(seconds: number): string {
  const whole = Math.max(0, seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, '0')}`;
}
