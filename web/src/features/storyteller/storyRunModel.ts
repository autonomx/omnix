/**
 * An interactive run as the reader shows it: its pages in order with the move that led to each, and the
 * branches an undo or a "Continue from here" left behind (ST-3.1, ST-3.4). Nothing here decides what is
 * visible: the server keeps the visible run as one chain of `parent_page_id`.
 */
import type { StoryMove, StoryPage, StoryProject } from './api/storyClient';
import { truncate } from './storyModel';
import { pageText, visiblePages } from './storyProjectModel';

export type StoryRunStep = { page: StoryPage; move: StoryMove | null; number: number };

export type StoryBranch = {
  /** The branch's last page: opening it shows the branch. */
  tipId: string;
  /** The move that started the branch, or its first page's opening words. */
  label: string;
  /** The page of the visible run it leaves from; null when it leaves before the first page. */
  forkNumber: number | null;
  pageCount: number;
};

function movesByPage(project: StoryProject | null | undefined): Map<string, StoryMove> {
  return new Map((project?.moves ?? []).flatMap((move) => (move.page_id ? [[move.page_id, move] as const] : [])));
}

export function storyRun(project: StoryProject | null | undefined): StoryRunStep[] {
  const moves = movesByPage(project);
  return visiblePages(project).map((page, index) => ({ page, move: moves.get(page.id) ?? null, number: index + 1 }));
}

/** A move as the reader shows it: what the player wrote, or the suggestion they chose. */
export function moveText(move: StoryMove): string {
  return move.player_text.trim() || move.chosen_suggestion.trim();
}

/** Every hidden page that no page continues from ends a branch; the branch starts where it leaves the run. */
export function storyBranches(project: StoryProject | null | undefined): StoryBranch[] {
  const pages = project?.pages ?? [];
  const byId = new Map(pages.map((page) => [page.id, page]));
  const continued = new Set(pages.map((page) => page.parent_page_id).filter(Boolean));
  const runNumbers = new Map(storyRun(project).map((step) => [step.page.id, step.number]));
  const moves = movesByPage(project);
  return pages.filter((page) => page.hidden && !continued.has(page.id)).map((tip) => {
    let first = tip;
    let pageCount = 1;
    for (let parent = byId.get(first.parent_page_id ?? ''); parent?.hidden && pageCount <= pages.length; parent = byId.get(first.parent_page_id ?? '')) {
      first = parent;
      pageCount += 1;
    }
    const move = moves.get(first.id);
    const label = (move ? moveText(move) : '') || first.title.trim() || pageText(first).split('\n')[0] || 'A branch';
    return {
      tipId: tip.id,
      label: truncate(label, 60),
      forkNumber: runNumbers.get(first.parent_page_id ?? '') ?? null,
      pageCount,
    };
  });
}
