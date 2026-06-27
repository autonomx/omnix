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
    const afterWindow = paragraph.slice(index + match[0].length, index + match[0].length + 120);
    const beforeWindow = paragraph.slice(Math.max(0, index - 120), index);
    blocks.push(dialogueBlock(chapterId, order++, quote, cast, `${beforeWindow} ${afterWindow}`));
    lastIndex = index + match[0].length;
  }
  const remaining = paragraph.slice(lastIndex).trim();
  if (remaining) blocks.push(narrationBlock(chapterId, order++, remaining));
  if (!blocks.length && paragraph.trim()) blocks.push(narrationBlock(chapterId, order, paragraph.trim()));
  return blocks;
}

function narrationBlock(chapterId: string, order: number, text: string): StoryBlock {
  return { id: `${chapterId}-narration-${order}`, kind: 'narration', chapterId, text, speakerId: 'narrator', order };
}

function dialogueBlock(chapterId: string, order: number, text: string, cast: StoryCharacter[], context: string): StoryBlock {
  const attributed = inferSpeakerFromContext(context, cast);
  return {
    id: `${chapterId}-dialogue-${order}`,
    kind: 'dialogue',
    chapterId,
    text,
    speakerId: attributed?.id ?? 'narrator',
    speakerName: attributed?.displayName ?? 'Narrator',
    order,
    confidence: attributed ? 0.78 : 0.2,
    attributionEvidence: attributed ? 'nearby explicit character name' : 'no reliable attribution',
  };
}

function inferSpeakerFromContext(context: string, cast: StoryCharacter[]): StoryCharacter | null {
  const lowerContext = context.toLowerCase();
  return cast.find((character) => character.id !== 'narrator' && character.aliases.some((alias) => lowerContext.includes(alias.toLowerCase()))) ?? null;
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
