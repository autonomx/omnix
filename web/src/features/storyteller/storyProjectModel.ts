/** A story project as the workspace shows it: its manuscript text, the latest page and library entries (ST-1.2). */
import type { StoryPage, StoryProject, StoryProjectSummary } from './api/storyClient';
import { countWords, truncate } from './storyModel';

export type StoryLibraryEntry = {
  id: string;
  title: string;
  subtitle: string;
  mode: StoryProjectSummary['mode'];
};

export function libraryEntry(project: StoryProjectSummary): StoryLibraryEntry {
  const kind = project.mode === 'interactive' ? 'interactive' : 'story';
  return {
    id: project.id,
    title: project.title.trim() || 'Untitled story',
    subtitle: `${project.word_count.toLocaleString()} words • ${kind}`,
    mode: project.mode,
  };
}

export function visiblePages(project: StoryProject | null | undefined): StoryPage[] {
  return (project?.pages ?? []).filter((page) => !page.hidden);
}

export function pageText(page: StoryPage): string {
  return page.blocks.map((block) => block.text.trim()).filter(Boolean).join('\n\n');
}

/**
 * One line of the manuscript as it is shown: a heading, a paragraph of narration, or a spoken line with its speaker.
 * Each names the page it comes from, and a line its block on that page, so an edit or a selection maps back to
 * the blocks (ST-6.1, ST-6.2).
 */
export type ManuscriptItem =
  | { kind: 'chapter'; id: string; pageId: string; number: number; text: string }
  | { kind: 'scene'; id: string; pageId: string; number: number; text: string }
  | { kind: 'narration'; pageId: string; block: number; text: string }
  | { kind: 'dialogue'; pageId: string; block: number; text: string; speakerId: string | null; speakerName: string; unverified: boolean };

/**
 * The manuscript from the pages' blocks: the pages in order, with a chapter heading where a story has more
 * than one chapter and a scene heading for each page that continues a chapter. A spoken line carries the
 * speaker the server recorded, named from the cast; one whose speaker is not in the cast is flagged.
 */
export function manuscriptItems(project: StoryProject | null | undefined, pages = visiblePages(project)): ManuscriptItem[] {
  const names = new Map((project?.characters ?? []).map((character) => [character.id, character.name]));
  const chapters = new Set(pages.map((page) => page.chapter));
  const items: ManuscriptItem[] = [];
  let chapter: number | null = null;
  let scene = 0;
  for (const page of pages) {
    if (page.chapter !== chapter) {
      chapter = page.chapter;
      scene = 0;
      if (chapters.size > 1 || chapter !== 1) {
        items.push({ kind: 'chapter', id: `story-chapter-${chapter}`, pageId: page.id, number: chapter, text: page.title.trim() || `Chapter ${chapter}` });
      }
    }
    scene += 1;
    if (scene > 1) {
      const text = page.title.trim() || firstSentence(pageText(page)) || `Scene ${scene}`;
      items.push({ kind: 'scene', id: `story-scene-${chapter}-${scene}`, pageId: page.id, number: scene, text });
    }
    page.blocks.forEach((block, index) => {
      const text = block.text.trim();
      if (!text) return;
      if (block.kind !== 'dialogue') {
        items.push({ kind: 'narration', pageId: page.id, block: index, text });
        return;
      }
      const speakerId = block.speaker_id?.trim() || null;
      const name = speakerId ? names.get(speakerId) : undefined;
      items.push({
        kind: 'dialogue',
        pageId: page.id,
        block: index,
        text,
        speakerId,
        speakerName: name ?? (speakerId || 'Unknown speaker'),
        unverified: block.attribution === 'unverified' || !name,
      });
    });
  }
  return items;
}

/** The manuscript as text, with "Chapter N:" and "Scene N:" heading lines that the outline reads (`deriveStoryOutline`). */
export function manuscriptText(items: ManuscriptItem[]): string | null {
  if (!items.length) return null;
  return items.map((item) => {
    if (item.kind === 'chapter') return `Chapter ${item.number}: ${item.text}`;
    if (item.kind === 'scene') return `Scene ${item.number}: ${item.text}`;
    return item.text;
  }).join('\n\n');
}

/** A spoken line's speaker for the Markdown export: bold, and marked when the cast does not have them. */
function markdownLine(item: ManuscriptItem): string {
  if (item.kind === 'chapter') return `## ${item.text}`;
  if (item.kind === 'scene') return `### ${item.text}`;
  if (item.kind === 'narration') return item.text;
  return `**${item.speakerName}${item.unverified ? ' (unverified)' : ''}:** ${item.text}`;
}

export function manuscriptMarkdown(items: ManuscriptItem[]): string {
  return items.map(markdownLine).join('\n\n');
}

/** The pages an interactive story shows: the last one written. */
export function latestPages(project: StoryProject | null | undefined): StoryPage[] {
  const pages = visiblePages(project);
  return pages.length ? [pages[pages.length - 1]] : [];
}

export function projectWordCount(project: StoryProject | null | undefined): number {
  return visiblePages(project).reduce((total, page) => total + countWords(pageText(page)), 0);
}

const versionKindLabels: Record<StoryProject['versions'][number]['kind'], string> = {
  rewrite: 'Rewrite',
  expand: 'Expanded',
  dialogue: 'Dialogue polish',
  summarize: 'Summary',
  kept_run: 'Kept run',
  manual: 'Saved',
};

export function versionLabel(version: StoryProject['versions'][number]): string {
  const selection = version.selection;
  if (!selection) return version.title.trim() || versionKindLabels[version.kind];
  // A selection version names its action and what happened to its proposal (ST-6.2).
  const status = { pending: 'waiting', accepted: 'accepted', rejected: 'rejected' }[selection.status];
  return `${versionKindLabels[version.kind]} of a selection (${status})`;
}

function firstSentence(text: string): string | null {
  const sentence = text.split(/\n/)[0]?.split(/[.!?]/)[0]?.trim();
  return sentence ? truncate(sentence, 48) : null;
}

/** A version's date, as the strip shows it. */
export function shortDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
