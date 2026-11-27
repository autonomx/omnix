/**
 * The story's plan as the Plan panel edits it (ST-5.1): chapters of beats. The server replaces the plan
 * whole; a beat sent back with its id keeps it, and the page drafted from it.
 */
import type { StoryOutlineChapter, StoryOutlineChapterInput, StoryPage } from './api/storyClient';
import { pageText } from './storyProjectModel';

/** The server's caps (`story/contracts`): chapters, beats in a chapter, and a beat's length. */
export const planChaptersMax = 40;
export const planBeatsMax = 12;
export const beatMaxChars = 600;
export const chapterTitleMaxChars = 200;
/** The chapters a planning job may ask for (`story/outline.PLANNED_CHAPTERS_MAX`). */
export const plannedChaptersMax = 20;

export type BeatDraft = { id: string | null; text: string; pageId: string | null };
export type ChapterDraft = { title: string; beats: BeatDraft[] };

export function planDraft(outline: StoryOutlineChapter[]): ChapterDraft[] {
  return outline.map((chapter) => ({
    title: chapter.title,
    beats: chapter.beats.map((beat) => ({ id: beat.id, text: beat.text, pageId: beat.page_id })),
  }));
}

/** The plan as the server takes it: empty beats left out, and a chapter with neither title nor beats. */
export function planInput(chapters: ChapterDraft[]): StoryOutlineChapterInput[] {
  return chapters
    .map((chapter) => ({
      title: chapter.title.trim().slice(0, chapterTitleMaxChars),
      beats: chapter.beats
        .map((beat) => ({ id: beat.id, text: beat.text.trim().slice(0, beatMaxChars) }))
        .filter((beat) => beat.text)
        .slice(0, planBeatsMax),
    }))
    .filter((chapter) => chapter.title || chapter.beats.length)
    .slice(0, planChaptersMax);
}

export function samePlan(left: ChapterDraft[], right: ChapterDraft[]): boolean {
  return JSON.stringify(planInput(left)) === JSON.stringify(planInput(right));
}

export function withChapterTitle(chapters: ChapterDraft[], index: number, title: string): ChapterDraft[] {
  return chapters.map((chapter, at) => (at === index ? { ...chapter, title } : chapter));
}

export function withBeatText(chapters: ChapterDraft[], index: number, beatIndex: number, text: string): ChapterDraft[] {
  return chapters.map((chapter, at) => (at === index
    ? { ...chapter, beats: chapter.beats.map((beat, beatAt) => (beatAt === beatIndex ? { ...beat, text } : beat)) }
    : chapter));
}

export function withNewBeat(chapters: ChapterDraft[], index: number): ChapterDraft[] {
  return chapters.map((chapter, at) => (at === index && chapter.beats.length < planBeatsMax
    ? { ...chapter, beats: [...chapter.beats, { id: null, text: '', pageId: null }] }
    : chapter));
}

export function withoutBeat(chapters: ChapterDraft[], index: number, beatIndex: number): ChapterDraft[] {
  return chapters.map((chapter, at) => (at === index
    ? { ...chapter, beats: chapter.beats.filter((_, beatAt) => beatAt !== beatIndex) }
    : chapter));
}

export function withNewChapter(chapters: ChapterDraft[]): ChapterDraft[] {
  if (chapters.length >= planChaptersMax) return chapters;
  return [...chapters, { title: '', beats: [{ id: null, text: '', pageId: null }] }];
}

export function withoutChapter(chapters: ChapterDraft[], index: number): ChapterDraft[] {
  return chapters.filter((_, at) => at !== index);
}

/** Where a drafted beat's page is: its chapter and opening words, or null when the page is no longer in the story. */
export function draftedPage(pageId: string | null, pages: StoryPage[]): { chapter: number; opening: string } | null {
  const page = pageId ? pages.find((candidate) => candidate.id === pageId) : undefined;
  if (!page) return null;
  const text = pageText(page).replace(/\s+/g, ' ').trim();
  return { chapter: page.chapter, opening: text.length > 80 ? `${text.slice(0, 80)}…` : text };
}
