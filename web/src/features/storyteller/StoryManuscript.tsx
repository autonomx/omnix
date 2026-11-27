import './StoryManuscript.css';
import { type ReactNode, useEffect, useRef, useState } from 'react';
import type { StoryBlock, StoryProject, StoryVersionSummary } from './api/storyClient';
import { StoryPageEditor } from './StoryPageEditor';
import { ManuscriptLines } from './StoryPanels';
import { StoryProposals } from './StoryProposals';
import type { StorySelectionAction, StorySelectionRange } from './storyModel';
import { type ManuscriptItem, visiblePages } from './storyProjectModel';
import { type StoryReadAloud, useStoryReadAloud } from './useStoryReadAloud';

const reworkActions: Array<{ action: StorySelectionAction; label: string }> = [
  { action: 'rewrite', label: 'Rewrite' },
  { action: 'expand', label: 'Expand' },
  { action: 'dialogue', label: 'Polish dialogue' },
];

/** Blocks `[start, end)` of a page, before the text they hold is read from the page. */
type BlockRange = Omit<StorySelectionRange, 'texts'>;

/** Whether the range takes in any of the line's text, not only the boundary at its start or end. */
function takesText(range: Range, line: Element): boolean {
  if (!range.intersectsNode(line)) return false;
  const part = document.createRange();
  part.selectNodeContents(line);
  if (range.compareBoundaryPoints(Range.START_TO_START, part) > 0) part.setStart(range.startContainer, range.startOffset);
  if (range.compareBoundaryPoints(Range.END_TO_END, part) < 0) part.setEnd(range.endContainer, range.endOffset);
  return part.toString().trim() !== '';
}

/**
 * The writer's text selection as blocks of one page; null when it is empty or spans pages. A line counts
 * only when some of its text is selected: a triple-click or a drag to the edge of the next paragraph ends
 * at that paragraph's start, which does not select it.
 */
function selectedBlocks(root: HTMLElement): BlockRange | null {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  const lines = [...root.querySelectorAll<HTMLElement>('[data-block-index][data-page-id]')].filter((line) => takesText(range, line));
  const pageIds = new Set(lines.map((line) => line.dataset.pageId));
  if (!lines.length || pageIds.size !== 1) return null;
  const blocks = lines.map((line) => Number(line.dataset.blockIndex));
  return { pageId: lines[0].dataset.pageId ?? '', start: Math.min(...blocks), end: Math.max(...blocks) + 1 };
}

/** The manuscript's lines grouped by the page they come from, in order. */
function pageGroups(items: ManuscriptItem[]): Array<{ pageId: string; items: ManuscriptItem[] }> {
  const groups: Array<{ pageId: string; items: ManuscriptItem[] }> = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last?.pageId === item.pageId) last.items.push(item);
    else groups.push({ pageId: item.pageId, items: [item] });
  }
  return groups;
}

/**
 * The writing manuscript (ST-6.1, ST-6.2): each page with its own edit and rework actions, a toolbar that
 * reworks the paragraphs the writer selects, and the proposals waiting for an answer above the text.
 *
 * The shown pages may be read aloud as in the interactive reader: from a page on, or the whole chapter, each
 * page read on into the next, the line being heard marked. Opening a page to edit, or leaving the chapter, stops it.
 */
export function StoryManuscript({ project, items, disabled, onRework, onSavePage, onAccept, onReject, children }: {
  project: StoryProject;
  items: ManuscriptItem[];
  disabled: boolean;
  onRework: (action: StorySelectionAction, range: StorySelectionRange) => void;
  onSavePage: (pageId: string, pageNumber: number, blocks: StoryBlock[], baseBlocks: StoryBlock[]) => Promise<unknown>;
  onAccept: (version: StoryVersionSummary, pageNumber: number) => Promise<unknown>;
  onReject: (version: StoryVersionSummary) => Promise<unknown>;
  /** Shown above the pages: the chapter heading. */
  children?: ReactNode;
}) {
  const prose = useRef<HTMLDivElement>(null);
  const [editingPage, setEditing] = useState<string | null>(null);
  const [selection, setSelected] = useState<BlockRange | null>(null);
  const pages = visiblePages(project);
  // A restore or a new page set can take away the page being edited or selected; the editor and the toolbar go with it.
  const editing = editingPage && pages.some((page) => page.id === editingPage) ? editingPage : null;
  const selected = selection && pages.some((page) => page.id === selection.pageId && page.blocks.length >= selection.end) ? selection : null;
  const pageNumber = (pageId: string) => pages.findIndex((page) => page.id === pageId) + 1;
  const readSelection = () => setSelected(prose.current ? selectedBlocks(prose.current) : null);
  const rework = (action: StorySelectionAction, range: BlockRange) => {
    window.getSelection()?.removeAllRanges();
    setSelected(null);
    const page = pages.find((candidate) => candidate.id === range.pageId);
    if (!page) return;
    // The selected text goes with the job, so a page edited before it runs is not reworked at old indices.
    onRework(action, { ...range, texts: page.blocks.slice(range.start, range.end).map((block) => block.text) });
  };
  const selectedLabel = selected
    ? `${selected.end - selected.start === 1 ? '1 paragraph' : `${selected.end - selected.start} paragraphs`} of page ${pageNumber(selected.pageId)} selected`
    : '';
  const groups = pageGroups(items).filter((group) => pages.some((page) => page.id === group.pageId));
  const shownIds = groups.map((group) => group.pageId);
  const aloud = useStoryReadAloud(project);
  const { stop: stopReading } = aloud;
  const readingPage = aloud.speaking?.pageId ?? null;
  const shownKey = shownIds.join(' ');
  useEffect(() => {
    if (readingPage && !shownKey.split(' ').includes(readingPage)) stopReading();
  }, [readingPage, shownKey, stopReading]);
  const readFrom = (pageId: string) => {
    const at = shownIds.indexOf(pageId);
    if (at >= 0) aloud.play(pageId, shownIds.slice(at + 1));
  };
  const edit = (pageId: string) => {
    aloud.stop();
    setEditing(pageId);
  };

  return (
    <>
      <StoryProposals disabled={disabled} onAccept={onAccept} onReject={onReject} project={project} />
      {children}
      {aloud.speaking ? null : (
        <section aria-label="Read aloud" className="storyteller-read-aloud">
          <button disabled={!shownIds.length || editing !== null} onClick={() => readFrom(shownIds[0])} type="button">
            Read this chapter aloud
          </button>
          {aloud.silent ? <p role="status">The speech service is not available; the page stands as text.</p> : null}
        </section>
      )}
      {selected ? (
        <div aria-label="Selection" className="storyteller-selection-toolbar" role="toolbar">
          <span>{selectedLabel}</span>
          {reworkActions.map(({ action, label }) => (
            <button disabled={disabled} key={action} type="button" onClick={() => rework(action, selected)}>{`${label} selection`}</button>
          ))}
          <button type="button" onClick={() => { window.getSelection()?.removeAllRanges(); setSelected(null); }}>Clear</button>
        </div>
      ) : null}
      <div className="storyteller-prose" onKeyUp={readSelection} onMouseUp={readSelection} ref={prose}>
        {groups.map((group) => {
          const page = pages.find((candidate) => candidate.id === group.pageId);
          if (!page) return null;
          const number = pageNumber(page.id);
          if (editing === page.id) {
            return (
              <StoryPageEditor
                blocks={page.blocks}
                characters={project.characters}
                key={page.id}
                onCancel={() => setEditing(null)}
                onSave={async (blocks, baseBlocks) => { await onSavePage(page.id, number, blocks, baseBlocks); setEditing(null); }}
                pageNumber={number}
              />
            );
          }
          return (
            <section aria-label={`Page ${number}`} className="storyteller-page" data-page-id={page.id} key={page.id}>
              <div className="storyteller-page-tools">
                <button aria-label={`Read page ${number} aloud`} disabled={editing !== null} type="button" onClick={() => readFrom(page.id)}>
                  Read aloud
                </button>
                <button aria-label={`Edit page ${number}`} disabled={editing !== null} type="button" onClick={() => edit(page.id)}>Edit</button>
                {reworkActions.map(({ action, label }) => (
                  <button
                    aria-label={`${label} page ${number}`}
                    disabled={disabled}
                    key={action}
                    type="button"
                    onClick={() => rework(action, { pageId: page.id, start: 0, end: page.blocks.length })}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <ManuscriptLines items={group.items} speaking={readingPage === page.id ? aloud.speaking?.line ?? null : null} />
            </section>
          );
        })}
      </div>
      {aloud.speaking ? <ReadingBar aloud={aloud} pageNumber={readingPage ? pageNumber(readingPage) : 0} /> : null}
    </>
  );
}

/** While a page is heard: a bar held to the foot of the view with the page being read, pause or resume, skip and stop. */
function ReadingBar({ aloud, pageNumber }: { aloud: StoryReadAloud; pageNumber: number }) {
  return (
    <section aria-label="Read aloud" className="storyteller-read-aloud reading">
      <span role="status">{pageNumber ? `Reading page ${pageNumber}` : 'Reading'}{aloud.paused ? ', paused' : ''}</span>
      {aloud.paused
        ? <button onClick={aloud.resume} type="button">Resume</button>
        : <button onClick={aloud.pause} type="button">Pause</button>}
      <button onClick={aloud.skip} type="button">Skip line</button>
      <button onClick={aloud.stop} type="button">Stop</button>
    </section>
  );
}
