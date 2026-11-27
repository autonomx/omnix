/**
 * Interactive story mode: the whole run with the player's moves between its pages, scrolled to the newest
 * page (ST-3.1), the model's suggested moves (ST-3.2), undo and branches (ST-3.4), "writing…" while the
 * page is written (ST-3.5) and "Keep this run" (ST-3.6). A page is read aloud in the cast's voices, the line
 * being heard marked; with "Read new pages aloud" each new page is read as it arrives, and typing a response
 * stops the reading (ST-4.3).
 */
import { Button } from '@mantine/core';
import { useEffect, useMemo, useRef } from 'react';
import { isJobSettled } from '../../api/jobs';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill } from '../../design/primitives';
import type { StoryProject } from './api/storyClient';
import type { NarrateInAudiobook } from './useNarrateInAudiobook';
import { ManuscriptLines, StoryEmptyState } from './StoryPanels';
import { manuscriptItems } from './storyProjectModel';
import { type StoryRunStep, moveText, storyBranches, storyRun } from './storyRunModel';
import { type StoryReadAloud, useStoryReadAloud } from './useStoryReadAloud';

/** The library calls the reader makes; each returns the project as it now stands. */
export type StoryRunLibrary = {
  undoMove: (projectId: string) => Promise<StoryProject>;
  openPage: (projectId: string, pageId: string) => Promise<StoryProject>;
  keepRun: (projectId: string, title: string) => Promise<StoryProject>;
};

const pageAnchor = (pageId: string) => `story-run-page-${pageId}`;

/**
 * Reads aloud the page that joins the run after a move, when the reader asked for new pages to be read. It
 * keeps the story and the page the run ended at when the move was asked for; opening another story forgets
 * them, so that story's pages are not mistaken for the new one.
 */
function useReadNewPage({ projectId, busy, jobStatus, lastPageId, autoplay, play }: {
  projectId: string | null;
  busy: boolean;
  jobStatus: string | undefined;
  lastPageId: string | undefined;
  autoplay: boolean;
  play: (pageId: string) => void;
}) {
  const askedAfter = useRef<{ projectId: string; pageId: string } | null>(null);
  useEffect(() => {
    if (askedAfter.current && askedAfter.current.projectId !== projectId) askedAfter.current = null;
    if (busy) {
      if (projectId) askedAfter.current ??= { projectId, pageId: lastPageId ?? '' };
      return;
    }
    if (askedAfter.current === null) return;
    if (jobStatus && jobStatus !== 'completed') {
      askedAfter.current = null;  // failed or cancelled: no new page
      return;
    }
    if (!lastPageId || lastPageId === askedAfter.current.pageId) return;  // the new page is still on its way
    askedAfter.current = null;
    if (autoplay) play(lastPageId);
  }, [autoplay, busy, jobStatus, lastPageId, play, projectId]);
}

/** Scrolls the reader, not the whole workspace, to a page of the run. */
function scrollReaderTo(reader: HTMLElement | null, pageId: string, behavior: ScrollBehavior): void {
  const page = document.getElementById(pageAnchor(pageId));
  if (page && reader) reader.scrollTo?.({ top: page.offsetTop, behavior });
}

export function StoryModePanel({
  activeChapterLabel, isLoading, job, library, module, narrate, onMove, pending, project, report, response, setResponse, storyTitle,
}: {
  activeChapterLabel: string;
  isLoading: boolean;
  /** The story job being followed, if any. */
  job: { status: string } | null;
  /** Hands a story to Audiobook and opens the book (ST-4.4). */
  narrate: NarrateInAudiobook;
  library: StoryRunLibrary;
  module: OmnixModuleDefinition;
  onMove: (moveText: string, options?: { suggested?: boolean }) => void;
  /** The job is being created. */
  pending: boolean;
  project: StoryProject | null;
  /** Runs a library call and reports its outcome to the writer. */
  report: (task: () => Promise<string | null>) => void;
  response: string;
  setResponse: (value: string) => void;
  storyTitle: string;
}) {
  const run = useMemo(() => storyRun(project), [project]);
  const branches = useMemo(() => storyBranches(project), [project]);
  const last = run.length ? run[run.length - 1] : null;
  const writing = job?.status === 'running';
  // While a page is on its way, the run stays as it is: the page joins the run it was asked for.
  const busy = pending || Boolean(job && !isJobSettled(job.status));
  const reader = useRef<HTMLDivElement>(null);
  const showPage = (pageId: string) => scrollReaderTo(reader.current, pageId, 'smooth');
  const lastPageId = last?.page.id;
  useEffect(() => {
    if (lastPageId) scrollReaderTo(reader.current, lastPageId, 'auto');
  }, [lastPageId]);
  const aloud = useStoryReadAloud(project);
  const { autoplay, play } = aloud;
  useReadNewPage({ projectId: project?.id ?? null, busy, jobStatus: job?.status, lastPageId, autoplay, play });

  const undo = () => project && report(async () => {
    await library.undoMove(project.id);
    return 'Undid the last move. Its page is kept under Other branches.';
  });
  const openPage = (pageId: string, message: string) => project && report(async () => {
    await library.openPage(project.id, pageId);
    return message;
  });
  // The run is kept first, so the book is that version of the story: its pages, not the player's moves (Q-ST1).
  const narrateRun = () => project && report(async () => {
    const kept = await library.keepRun(project.id, storyTitle);
    const version = [...kept.versions].filter((item) => item.kind === 'kept_run')
      .sort((a, b) => b.version_number - a.version_number)[0];
    return narrate(kept, storyRun(kept).map((step) => step.page), { title: storyTitle, versionId: version?.id });
  });
  const keepRun = () => project && report(async () => {
    const kept = await library.keepRun(project.id, storyTitle);
    const newest = Math.max(0, ...kept.versions.map((version) => version.version_number));
    return `Kept this run as version ${newest}; find it in Story versions.`;
  });

  return (
    <section className="story-mode-panel" aria-label="Interactive story mode">
      <div className="story-mode-reader" ref={reader}>
        <div className="storyteller-manuscript-meta">
          <span>{activeChapterLabel}</span>
          <span>{run.length === 1 ? '1 page' : `${run.length} pages`}</span>
        </div>
        <h2>{storyTitle}</h2>
        <div className="storyteller-flourish" aria-hidden="true"><span /><strong>◇</strong><span /></div>
        {run.length ? run.map((step) => (
          <StoryRunPage
            busy={busy}
            isLast={step === last}
            key={step.page.id}
            onContinueFrom={() => openPage(step.page.id, `Back at page ${step.number}. Your next move starts a new branch.`)}
            onRead={() => aloud.play(step.page.id)}
            project={project}
            speaking={aloud.speaking?.pageId === step.page.id ? aloud.speaking.line : null}
            step={step}
          />
        )) : <StoryEmptyState isLoading={isLoading} module={module} />}
      </div>
      <aside className="story-mode-controls" aria-label="Interactive story mode controls">
        <div className="storyteller-panel-heading">
          <div><p className="eyebrow">Interactive story mode</p><h3>Your next move</h3></div>
          <OmnixStatusPill>{writing ? 'writing…' : busy ? 'continuing' : 'ready'}</OmnixStatusPill>
        </div>
        <label>
          Write your response
          <textarea
            aria-label="Interactive story mode response"
            onChange={(event) => {
              aloud.stop();
              setResponse(event.target.value);
            }}
            placeholder="I examine the glowing door, but keep one hand on the charm."
            rows={5}
            value={response}
          />
        </label>
        <Button disabled={busy || !response.trim()} loading={pending} onClick={() => onMove(response)} type="button">
          Continue with my response
        </Button>
        <StoryReadAloudControls aloud={aloud} lastPageId={lastPageId} />
        {last?.page.suggested_moves.length ? (
          <div className="story-mode-suggestions">
            <p className="eyebrow">Suggested next moves</p>
            {last.page.suggested_moves.map((move) => (
              <button disabled={busy} key={move} type="button" onClick={() => onMove(move, { suggested: true })}>{move}</button>
            ))}
          </div>
        ) : null}
        <div className="story-mode-run-actions">
          <button disabled={busy || !last?.move} onClick={undo} type="button">Undo last move</button>
          <button disabled={busy || !run.length} onClick={keepRun} type="button">Keep this run</button>
          <button disabled={busy || !run.length} onClick={narrateRun} type="button">Narrate in Audiobook</button>
        </div>
        {run.length > 1 ? (
          <nav className="story-mode-jump" aria-label="Pages of this run">
            <p className="eyebrow">Pages</p>
            {run.map((step) => (
              <button key={step.page.id} onClick={() => showPage(step.page.id)} type="button">
                {step.number}. {step.move ? moveText(step.move) : step.page.title.trim() || 'Opening'}
              </button>
            ))}
          </nav>
        ) : null}
        {branches.length ? (
          <section className="story-mode-branches" aria-label="Other branches">
            <p className="eyebrow">Other branches</p>
            {branches.map((branch) => (
              <div key={branch.tipId}>
                <span>
                  {branch.forkNumber ? `After page ${branch.forkNumber}` : 'From the start'}: {branch.label}
                  {branch.pageCount > 1 ? ` (${branch.pageCount} pages)` : ''}
                </span>
                <button
                  aria-label={`Open the branch ${branch.label}`}
                  disabled={busy}
                  onClick={() => openPage(branch.tipId, 'Opened that branch.')}
                  type="button"
                >
                  Open
                </button>
              </div>
            ))}
          </section>
        ) : null}
      </aside>
    </section>
  );
}

function StoryReadAloudControls({ aloud, lastPageId }: { aloud: StoryReadAloud; lastPageId: string | undefined }) {
  return (
    <section className="story-mode-read-aloud" aria-label="Read aloud">
      <p className="eyebrow">Read aloud</p>
      {aloud.speaking ? (
        <div className="story-mode-run-actions">
          {aloud.paused
            ? <button onClick={aloud.resume} type="button">Resume</button>
            : <button onClick={aloud.pause} type="button">Pause</button>}
          <button onClick={aloud.skip} type="button">Skip line</button>
          <button onClick={aloud.stop} type="button">Stop</button>
        </div>
      ) : (
        <button disabled={!lastPageId} onClick={() => lastPageId && aloud.play(lastPageId)} type="button">
          Read the newest page
        </button>
      )}
      <label className="story-mode-autoplay">
        <input checked={aloud.autoplay} onChange={(event) => aloud.setAutoplay(event.target.checked)} type="checkbox" />
        Read new pages aloud
      </label>
      {aloud.silent ? <p role="status">The speech service is not available; the page stands as text.</p> : null}
    </section>
  );
}

function StoryRunPage({ busy, isLast, onContinueFrom, onRead, project, speaking, step }: {
  busy: boolean;
  isLast: boolean;
  onContinueFrom: () => void;
  onRead: () => void;
  project: StoryProject | null;
  /** The line of this page being read aloud, if any. */
  speaking: number | null;
  step: StoryRunStep;
}) {
  const lines = manuscriptItems(project, [step.page]).filter((item) => item.kind === 'narration' || item.kind === 'dialogue');
  return (
    <article aria-label={`Page ${step.number}`} className="story-mode-page" id={pageAnchor(step.page.id)}>
      {step.move ? <p className="story-mode-move"><span>Your move</span> {moveText(step.move)}</p> : null}
      <ManuscriptLines items={lines} speaking={speaking} />
      <button aria-label={`Read page ${step.number} aloud`} className="story-mode-read-page" onClick={onRead} type="button">
        Read aloud
      </button>
      {isLast ? null : (
        <button className="story-mode-continue-from" disabled={busy} onClick={onContinueFrom} type="button">
          Continue from here
        </button>
      )}
    </article>
  );
}
