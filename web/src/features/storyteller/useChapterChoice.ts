import { useState } from 'react';
import type { StoryProject } from './api/storyClient';
import { plannedChaptersMax } from './storyPlanModel';
import { visiblePages } from './storyProjectModel';

export interface ChapterChoice {
  /** The chapter the next Generate writes. */
  chapter: number;
  setChapter: (chapter: number) => void;
  /** The open written story that Generate adds to; null when Generate starts a new story. */
  story: StoryProject | null;
  /** The open story's last chapter (0 with no story open). */
  lastChapter: number;
  min: number;
  max: number;
  /** How many chapters one Generate writes (1 to plannedChaptersMax): `chapter` first, then each next one. */
  count: number;
  setCount: (count: number) => void;
}

/** The open story's last chapter, as the job counts it: the highest chapter among its visible pages. */
export function lastChapterOf(project: StoryProject | null | undefined): number {
  return visiblePages(project).reduce((last, page) => Math.max(last, page.chapter), 0);
}

/**
 * Where the next Generate writes. With a written story open it adds to that story: its last chapter goes on, or
 * the chapter after it opens (the job writes nowhere else). With none open it starts a new story, at chapter 1.
 */
export function useChapterChoice(project: StoryProject | null): ChapterChoice {
  const story = project && project.mode === 'writing' && visiblePages(project).length ? project : null;
  const lastChapter = lastChapterOf(story);
  const [chapter, setChapterState] = useState(1);
  const [count, setCountState] = useState(1);

  // Opening a story points at its last chapter; between opens the choice stays inside what the story allows.
  const storyId = story?.id ?? null;
  const [openedId, setOpenedId] = useState(storyId);
  if (openedId !== storyId) {
    setOpenedId(storyId);
    setChapterState(storyId ? lastChapter : 1);
  }
  const min = story ? lastChapter : 1;
  const max = story ? lastChapter + 1 : 1;
  const bounded = Math.min(max, Math.max(min, chapter));
  const setChapter = (next: number) => setChapterState(Math.min(max, Math.max(min, Math.floor(next))));
  const setCount = (next: number) => setCountState(Math.min(plannedChaptersMax, Math.max(1, Math.floor(next) || 1)));
  return { chapter: bounded, setChapter, story, lastChapter, min, max, count, setCount };
}
