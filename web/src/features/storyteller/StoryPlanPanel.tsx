import './StoryPlanPanel.css';
import { useState } from 'react';
import type { StoryOutlineChapterInput, StoryProject } from './api/storyClient';
import type { SaveFeedback } from './storyModel';
import {
  type ChapterDraft, beatMaxChars, chapterTitleMaxChars, draftedPage, planBeatsMax, planDraft, planInput, plannedChaptersMax,
  samePlan, withBeatText, withChapterTitle, withNewBeat, withNewChapter, withoutBeat, withoutChapter,
} from './storyPlanModel';
import { visiblePages } from './storyProjectModel';

/**
 * The plan (ST-5.1): the story as chapters of beats, planned by the model, edited by the writer, and
 * drafted one beat at a time into its chapter. Unsaved edits are kept against the plan they were made on;
 * planning or drafting waits until they are saved.
 */
export function StoryPlanPanel({ project, pending, onPlan, onDraftBeat, saveOutline, onFeedback }: {
  project: StoryProject | null;
  pending: boolean;
  onPlan: (chapters: number) => void;
  onDraftBeat: (beatId: string) => void;
  saveOutline: (projectId: string, chapters: StoryOutlineChapterInput[]) => Promise<unknown>;
  onFeedback: (feedback: SaveFeedback) => void;
}) {
  const outline = project?.outline ?? [];
  // An edit belongs to one project's saved plan: it goes when the plan changes on the server or another story opens.
  const source = `${project?.id ?? ''}:${JSON.stringify(outline)}`;
  const [edit, setEdit] = useState<{ source: string; chapters: ChapterDraft[] } | null>(null);
  const [chapterCount, setChapterCount] = useState(5);
  const [busy, setBusy] = useState(false);
  const saved = planDraft(outline);
  const chapters = edit && edit.source === source ? edit.chapters : saved;
  const dirty = !samePlan(chapters, saved);
  const change = (next: ChapterDraft[]) => setEdit({ source, chapters: next });
  const beats = outline.reduce((total, chapter) => total + chapter.beats.length, 0);
  const drafted = outline.reduce((total, chapter) => total + chapter.beats.filter((beat) => beat.page_id).length, 0);
  const pages = visiblePages(project);

  const plan = () => {
    if (outline.length && !window.confirm('Plan the story again? The new plan replaces this one.')) return;
    onPlan(chapterCount);
  };
  const save = () => {
    if (!project) return;
    setBusy(true);
    void saveOutline(project.id, planInput(chapters))
      .then(() => setEdit(null))
      .catch((caught: unknown) => onFeedback({
        kind: 'error',
        message: caught instanceof Error && caught.message ? caught.message : 'The plan could not be saved.',
      }))
      .finally(() => setBusy(false));
  };

  return (
    <details className="storyteller-toolbox storyteller-plan" open={outline.length > 0 || undefined}>
      <summary>
        <span>
          <strong>Plan</strong>
          <small>Chapters and beats, drafted one beat at a time</small>
        </span>
        <em>{beats ? `${drafted} of ${beats} beats drafted` : 'Open'}</em>
      </summary>
      <div className="storyteller-plan-body">
        <form
          aria-label="Plan the story"
          className="storyteller-plan-start"
          onSubmit={(event) => { event.preventDefault(); plan(); }}
        >
          <label>
            Chapters
            <input
              max={plannedChaptersMax}
              min={1}
              type="number"
              value={chapterCount}
              onChange={(event) => setChapterCount(Math.min(plannedChaptersMax, Math.max(1, Number(event.currentTarget.value) || 1)))}
            />
          </label>
          <button type="submit" disabled={pending || dirty}>{outline.length ? 'Plan again' : 'Plan the story'}</button>
        </form>
        {chapters.length ? (
          <ol className="storyteller-plan-chapters">
            {chapters.map((chapter, index) => (
              <li key={`chapter-${index}`}>
                <header>
                  <span>Chapter {index + 1}</span>
                  <input
                    aria-label={`Chapter ${index + 1} title`}
                    maxLength={chapterTitleMaxChars}
                    placeholder="Title"
                    value={chapter.title}
                    onChange={(event) => change(withChapterTitle(chapters, index, event.currentTarget.value))}
                  />
                  <button type="button" disabled={busy} onClick={() => change(withoutChapter(chapters, index))}>Remove chapter {index + 1}</button>
                </header>
                <ol>
                  {chapter.beats.map((beat, beatIndex) => {
                    const page = draftedPage(beat.pageId, pages);
                    const name = `Chapter ${index + 1}, beat ${beatIndex + 1}`;
                    return (
                      <li key={beat.id ?? `new-${beatIndex}`}>
                        <textarea
                          aria-label={name}
                          maxLength={beatMaxChars}
                          rows={2}
                          value={beat.text}
                          onChange={(event) => change(withBeatText(chapters, index, beatIndex, event.currentTarget.value))}
                        />
                        <div>
                          {page ? <small>Drafted in chapter {page.chapter}: {page.opening}</small> : null}
                          {beat.id && !page ? (
                            <button type="button" disabled={pending || dirty || busy} onClick={() => onDraftBeat(beat.id as string)}>
                              Draft {name}
                            </button>
                          ) : null}
                          <button type="button" disabled={busy} onClick={() => change(withoutBeat(chapters, index, beatIndex))}>Remove {name}</button>
                        </div>
                      </li>
                    );
                  })}
                </ol>
                <button type="button" disabled={busy || chapter.beats.length >= planBeatsMax} onClick={() => change(withNewBeat(chapters, index))}>
                  Add beat to chapter {index + 1}
                </button>
              </li>
            ))}
          </ol>
        ) : <p>No plan yet. Plan the story from its premise and bible, or add chapters yourself.</p>}
        {project ? (
          <div className="storyteller-plan-actions">
            <button type="button" disabled={busy} onClick={() => change(withNewChapter(chapters))}>Add chapter</button>
            <button type="button" disabled={busy || !dirty} onClick={save}>Save plan</button>
            <button type="button" disabled={busy || !dirty} onClick={() => setEdit(null)}>Discard changes</button>
          </div>
        ) : null}
      </div>
    </details>
  );
}
