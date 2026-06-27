import { characterId, deriveStoryCast, type StoryCharacter } from './storyCast';

export type StoryBlockKind = 'narration' | 'dialogue';
export type StoryAudioScope = 'chapter' | 'selected_chapters' | 'full_story';

export interface StoryChapter {
  id: string;
  index: number;
  title: string;
  summary?: string;
  blocks: StoryBlock[];
  textFingerprint: string;
}

export type StoryBlock =
  | {
      id: string;
      kind: 'narration';
      chapterId: string;
      text: string;
      speakerId: 'narrator';
      order: number;
    }
  | {
      id: string;
      kind: 'dialogue';
      chapterId: string;
      text: string;
      speakerId: string;
      speakerName: string;
      order: number;
      confidence: number;
      attributionEvidence?: string;
    };

export interface StoryVoiceAssignment {
  characterId: string;
  voiceId: string;
  voiceLabel: string;
  style?: string;
  fallbackVoiceId?: string;
  updatedAt: string;
}

export interface StoryAudioManifest {
  id: string;
  storyId: string;
  scope: StoryAudioScope;
  chapterIds: string[];
  sourceFingerprint: string;
  voiceCastFingerprint: string;
  jobId?: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'stale';
  audioUrl?: string;
  downloadFilename?: string;
  durationSeconds?: number;
  createdAt: string;
  updatedAt: string;
}

export interface StoryDocument {
  id: string;
  title: string;
  premise: string;
  chapters: StoryChapter[];
  cast: StoryCharacter[];
  voiceCast: StoryVoiceAssignment[];
  audioManifests: StoryAudioManifest[];
  updatedAt: string;
}

const STORY_DOCUMENT_STORAGE_PREFIX = 'omnix.storyteller.document:';
const DIALOGUE_ATTRIBUTION_VERBS = [
  'said', 'asked', 'replied', 'answered', 'suggested', 'insisted', 'whispered', 'boomed',
  'murmured', 'muttered', 'shouted', 'called', 'declared', 'continued', 'added', 'sighed',
  'snapped', 'cried', 'exclaimed', 'noted', 'observed', 'warned', 'hissed', 'growled',
  'laughed', 'began', 'admitted', 'urged', 'promised', 'responded', 'remarked',
];

interface SpeakerAttribution {
  character: StoryCharacter;
  confidence: number;
  evidence: string;
}

export function storyDocumentStorageKey(storyId: string): string {
  return `${STORY_DOCUMENT_STORAGE_PREFIX}${storyId || 'draft'}`;
}

export function loadStoryDocument(storyId: string): StoryDocument | null {
  try {
    const raw = window.localStorage.getItem(storyDocumentStorageKey(storyId));
    if (!raw) return null;
    return validateStoryDocument(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function saveStoryDocument(document: StoryDocument): void {
  try {
    window.localStorage.setItem(storyDocumentStorageKey(document.id), JSON.stringify(document));
  } catch {
    // Local persistence is best-effort until backend story metadata APIs exist.
  }
}

export function buildStoryDocumentFromText({ title, premise = '', text, existing }: { title: string; premise?: string; text: string; existing?: StoryDocument | null }): StoryDocument {
  const storyId = storyIdFor(title, text);
  const cast = deriveStoryCast(text, existing?.cast ?? []);
  const chapters = splitTextIntoChapters(text, cast);
  return {
    id: storyId,
    title: title.trim() || 'Untitled story',
    premise,
    chapters,
    cast,
    voiceCast: existing?.voiceCast ?? [],
    audioManifests: existing?.audioManifests ?? [],
    updatedAt: new Date().toISOString(),
  };
}

export function allStoryBlocks(document: StoryDocument): StoryBlock[] {
  return document.chapters.flatMap((chapter) => chapter.blocks);
}

export function storyDocumentFingerprint(document: StoryDocument): string {
  return fingerprintText(document.chapters.map((chapter) => chapter.textFingerprint).join('|'));
}

export function fingerprintText(text: string): string {
  return `${text.length}:${text.slice(0, 80)}:${text.slice(-80)}`;
}

function splitTextIntoChapters(text: string, cast: StoryCharacter[]): StoryChapter[] {
  const normalized = normalizeStoryText(text);
  if (!normalized) return [];
  const paragraphs = normalized.split('\n\n');
  const chapters: Array<{ title: string; paragraphs: string[] }> = [];
  let current: { title: string; paragraphs: string[] } = { title: 'Chapter 1', paragraphs: [] };

  for (const paragraph of paragraphs) {
    if (/^chapter\s+\d+\b/i.test(paragraph)) {
      if (current.paragraphs.length) chapters.push(current);
      current = { title: paragraph.replace(/^#+\s*/, '').trim(), paragraphs: [paragraph] };
      continue;
    }
    current.paragraphs.push(paragraph);
  }
  if (current.paragraphs.length) chapters.push(current);

  return chapters.map((chapter, chapterIndex) => {
    const chapterId = `chapter-${chapterIndex + 1}`;
    const chapterText = chapter.paragraphs.join('\n\n');
    return {
      id: chapterId,
      index: chapterIndex,
      title: chapter.title,
      blocks: buildStoryBlocks(chapter.paragraphs, chapterId, cast),
      textFingerprint: fingerprintText(chapterText),
    };
  });
}

function buildStoryBlocks(paragraphs: string[], chapterId: string, cast: StoryCharacter[]): StoryBlock[] {
  const blocks: StoryBlock[] = [];
  let order = 0;
  for (const paragraph of paragraphs) {
    const parsed = splitParagraphIntoBlocks(paragraph, chapterId, order, cast);
    blocks.push(...parsed);
    order += parsed.length;
  }
  return blocks;
}

function splitParagraphIntoBlocks(paragraph: string, chapterId: string, startingOrder: number, cast: StoryCharacter[]): StoryBlock[] {
  const quotePattern = /[“"]([^”"]{2,})[”"]/g;
  const blocks: StoryBlock[] = [];
  let lastIndex = 0;
  let order = startingOrder;
  for (const match of paragraph.matchAll(quotePattern)) {
    const index = match.index ?? 0;
    const before = paragraph.slice(lastIndex, index).trim();
    if (before) blocks.push(narrationBlock(chapterId, order++, before));
    const quote = match[1].trim();
    const quoteEnd = index + match[0].length;
    const afterWindow = paragraph.slice(quoteEnd, quoteEnd + 180);
    const beforeWindow = paragraph.slice(Math.max(0, index - 180), index);
    blocks.push(dialogueBlock(chapterId, order++, quote, cast, beforeWindow, afterWindow));
    lastIndex = quoteEnd;
  }
  const remaining = paragraph.slice(lastIndex).trim();
  if (remaining) blocks.push(narrationBlock(chapterId, order++, remaining));
  if (!blocks.length && paragraph.trim()) blocks.push(narrationBlock(chapterId, order, paragraph.trim()));
  return blocks;
}

function narrationBlock(chapterId: string, order: number, text: string): StoryBlock {
  return { id: `${chapterId}-narration-${order}`, kind: 'narration', chapterId, text, speakerId: 'narrator', order };
}

function dialogueBlock(chapterId: string, order: number, text: string, cast: StoryCharacter[], beforeContext: string, afterContext: string): StoryBlock {
  const attributed = inferSpeakerFromContext(beforeContext, afterContext, cast);
  return {
    id: `${chapterId}-dialogue-${order}`,
    kind: 'dialogue',
    chapterId,
    text,
    speakerId: attributed?.character.id ?? 'narrator',
    speakerName: attributed?.character.displayName ?? 'Narrator',
    order,
    confidence: attributed?.confidence ?? 0.2,
    attributionEvidence: attributed?.evidence ?? 'no reliable attribution',
  };
}

function inferSpeakerFromContext(beforeContext: string, afterContext: string, cast: StoryCharacter[]): SpeakerAttribution | null {
  return inferTrailingNamedAttribution(afterContext, cast)
    ?? inferTrailingPronounAttribution(beforeContext, afterContext, cast)
    ?? inferNearestSpeaker(beforeContext, afterContext, cast);
}

function inferTrailingNamedAttribution(afterContext: string, cast: StoryCharacter[]): SpeakerAttribution | null {
  const immediate = afterContext.trimStart().slice(0, 140);
  for (const character of nonNarratorCast(cast)) {
    for (const alias of sortedAliases(character)) {
      const aliasPattern = escapeRegExp(alias);
      const verbPattern = DIALOGUE_ATTRIBUTION_VERBS.join('|');
      const direct = new RegExp(`^[,\\s—–-]*${aliasPattern}\\b(?:\\s+[a-z'’-]+){0,3}\\s+(?:${verbPattern})\\b`, 'i');
      if (direct.test(immediate)) {
        return { character, confidence: 0.96, evidence: `trailing dialogue attribution: ${alias}` };
      }
      const actionFirst = new RegExp(`^[,\\s—–-]*(?:${verbPattern})\\s+${aliasPattern}\\b`, 'i');
      if (actionFirst.test(immediate)) {
        return { character, confidence: 0.9, evidence: `trailing action-first attribution: ${alias}` };
      }
    }
  }
  return null;
}

function inferTrailingPronounAttribution(beforeContext: string, afterContext: string, cast: StoryCharacter[]): SpeakerAttribution | null {
  const immediate = afterContext.trimStart().slice(0, 80);
  const verbPattern = DIALOGUE_ATTRIBUTION_VERBS.join('|');
  if (!new RegExp(`^[,\\s—–-]*(?:he|she|they)\\s+(?:${verbPattern})\\b`, 'i').test(immediate)) return null;
  const nearest = nearestCharacterBeforeQuote(beforeContext, cast);
  return nearest ? { character: nearest, confidence: 0.74, evidence: 'pronoun attribution resolved to nearest preceding character' } : null;
}

function inferNearestSpeaker(beforeContext: string, afterContext: string, cast: StoryCharacter[]): SpeakerAttribution | null {
  const before = nearestCharacterBeforeQuote(beforeContext, cast);
  const after = nearestCharacterAfterQuote(afterContext, cast);
  if (after && after.index <= 60) {
    return { character: after.character, confidence: 0.62, evidence: 'nearest following character name' };
  }
  if (before) {
    return { character: before, confidence: 0.55, evidence: 'nearest preceding character name' };
  }
  return after ? { character: after.character, confidence: 0.5, evidence: 'nearby following character name' } : null;
}

function nearestCharacterBeforeQuote(context: string, cast: StoryCharacter[]): StoryCharacter | null {
  const lowerContext = context.toLowerCase();
  let best: { character: StoryCharacter; index: number } | null = null;
  for (const character of nonNarratorCast(cast)) {
    for (const alias of sortedAliases(character)) {
      const index = lowerContext.lastIndexOf(alias.toLowerCase());
      if (index >= 0 && (!best || index > best.index)) best = { character, index };
    }
  }
  return best?.character ?? null;
}

function nearestCharacterAfterQuote(context: string, cast: StoryCharacter[]): { character: StoryCharacter; index: number } | null {
  const lowerContext = context.toLowerCase();
  let best: { character: StoryCharacter; index: number } | null = null;
  for (const character of nonNarratorCast(cast)) {
    for (const alias of sortedAliases(character)) {
      const index = lowerContext.indexOf(alias.toLowerCase());
      if (index >= 0 && (!best || index < best.index)) best = { character, index };
    }
  }
  return best;
}

function nonNarratorCast(cast: StoryCharacter[]): StoryCharacter[] {
  return cast.filter((character) => character.id !== 'narrator');
}

function sortedAliases(character: StoryCharacter): string[] {
  return [...character.aliases, character.displayName]
    .map((alias) => alias.trim())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function validateStoryDocument(value: unknown): StoryDocument | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Partial<StoryDocument>;
  if (typeof record.id !== 'string' || typeof record.title !== 'string' || !Array.isArray(record.chapters)) return null;
  return record as StoryDocument;
}

function storyIdFor(title: string, text: string): string {
  return `${slugify(title || 'story')}:${fingerprintText(text)}`;
}

function normalizeStoryText(text: string): string {
  return text.replace(/\r\n/g, '\n').split('\n').map((line) => line.trim()).filter(Boolean).join('\n\n').trim();
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'story';
}

export { characterId };
