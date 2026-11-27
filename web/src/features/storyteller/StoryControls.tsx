/** The draft controls: provider, title, premise, tone, style, chapter and how many chapters to write. */
import { Button, Progress } from '@mantine/core';
import { useState } from 'react';
import { type UseMutationResult } from '@tanstack/react-query';
import { type FieldErrors, type UseFormHandleSubmit, type UseFormRegister } from 'react-hook-form';
import { type JobRecord } from '../../api/client';
import { OmnixStatusPill } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../../shared/FeatureSubmitFeedback';
import { jobProgressPercent } from '../../api/jobProgress';
import { jobOutputText, lineWords, pageLinesMax, pageLinesMin, premiseMaxChars, StoryGenerationRequest, StoryGenerationResult, StorytellerFormValues, styleOptions, toneMaxChars, toneOptions, truncate } from './storyModel';
import { plannedChaptersMax } from './storyPlanModel';
import type { ChapterChoice } from './useChapterChoice';

export interface StoryControlsProps {
  providers: Array<{ id: string; label: string }>;
  register: UseFormRegister<StorytellerFormValues>;
  errors: FieldErrors<StorytellerFormValues>;
  premiseLength: number;
  createJobMutation: UseMutationResult<StoryGenerationResult, Error, StoryGenerationRequest>;
  submitStatus: string;
  selectedTone: string;
  setSelectedTone: (tone: string) => void;
  writingStyle: string;
  setWritingStyle: (style: string) => void;
  /** Where Generate writes: the open story's last chapter or the next one, or a new story's first chapter. */
  chapterChoice: ChapterChoice;
  /** How long each new page is, in lines of prose (null for the usual length), and its setter. */
  pageLength: [number | null, (lines: number | null) => void];
  onGenerate: (values: StorytellerFormValues) => void;
  onAddChapter: () => void;
  handleSubmit: UseFormHandleSubmit<StorytellerFormValues>;
  latestJob: JobRecord | null;
}

/** The story's tone and mood: one of the usual ones, a preset's, or one the writer describes in their own words. */
function ToneChooser({ selectedTone, setSelectedTone }: { selectedTone: string; setSelectedTone: (tone: string) => void }) {
  const [customTones, setCustomTones] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const applyDraft = () => {
    const tone = draft.trim().replace(/\s+/gu, ' ');
    if (!tone) return;
    setCustomTones((current) => (current.includes(tone) ? current : [...current, tone]));
    setSelectedTone(tone);
    setDraft('');
  };
  return (
    <div className="storyteller-control-block">
      <span>Tone & mood</span>
      <div className="storyteller-chip-row">
        {/* A preset's own tone, and the writer's own, are offered alongside the usual ones (ST-5.2). */}
        {[...new Set([...toneOptions, ...customTones, selectedTone].filter(Boolean))].map((tone) => (
          <button aria-pressed={tone === selectedTone} className={tone === selectedTone ? 'active' : ''} key={tone} type="button" onClick={() => setSelectedTone(tone)}>{tone}</button>
        ))}
      </div>
      <div className="storyteller-custom-tone">
        <input
          aria-label="Your own tone and mood"
          maxLength={toneMaxChars}
          placeholder="Or describe your own: bittersweet, eerie calm…"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          // Enter uses the tone here rather than submitting the story form.
          onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); applyDraft(); } }}
        />
        <button type="button" disabled={!draft.trim()} onClick={applyDraft}>Use</button>
      </div>
    </div>
  );
}

/**
 * Lines per page: each chapter a Generate writes is one page at this length. A number outside the range the job asks for
 * is shown as such and sends the usual length; leaving the field settles it into the range.
 */
function PageLengthField({ pageLength: [pageLines, setPageLines] }: { pageLength: StoryControlsProps['pageLength'] }) {
  const [draft, setDraft] = useState(pageLines === null ? '' : String(pageLines));
  const typed = draft.trim() ? Number(draft) : null;
  const valid = typed === null || (Number.isInteger(typed) && typed >= pageLinesMin && typed <= pageLinesMax);
  const change = (text: string) => {
    setDraft(text);
    const lines = text.trim() ? Number(text) : null;
    setPageLines(lines !== null && Number.isInteger(lines) && lines >= pageLinesMin && lines <= pageLinesMax ? lines : null);
  };
  const settle = () => {
    if (typed === null || valid) return;
    if (!Number.isFinite(typed)) { change(''); return; }
    change(String(Math.min(pageLinesMax, Math.max(pageLinesMin, Math.round(typed)))));
  };
  return (
    <div className="storyteller-control-block storyteller-page-length">
      <label>
        Lines per page
        <input
          aria-describedby="storyteller-page-length-hint"
          aria-invalid={!valid}
          inputMode="numeric"
          max={pageLinesMax}
          min={pageLinesMin}
          placeholder="Usual length"
          step={1}
          type="number"
          value={draft}
          onBlur={settle}
          onChange={(event) => change(event.target.value)}
        />
      </label>
      <small id="storyteller-page-length-hint">
        {!valid ? `Choose ${pageLinesMin} to ${pageLinesMax} lines.`
          : pageLines ? `About ${pageLines * lineWords} words a page.` : 'Empty for the usual 400 to 800 words.'}
      </small>
    </div>
  );
}

/**
 * Chapters to write: how many chapters one Generate writes into the story, one page each. The first goes into the
 * chapter chosen above (a new story's chapter 1); each after it opens the next chapter.
 */
function ChapterCountField({ chapterChoice: { chapter, count, setCount, story, lastChapter } }: { chapterChoice: ChapterChoice }) {
  // A field the writer has cleared stays empty until the next digit; leaving it shows the count kept.
  const [draft, setDraft] = useState<string | null>(null);
  const last = chapter + count - 1;
  const continues = Boolean(story) && chapter === lastChapter;
  const hint = count === 1 ? (continues ? `Writes more of chapter ${chapter}.` : `Writes chapter ${chapter}.`)
    : continues ? `Chapter ${chapter} goes on, then ${count === 2 ? `chapter ${last} opens` : `chapters ${chapter + 1} to ${last} open`}.`
      : `Writes chapters ${chapter} to ${last}.`;
  return (
    <div className="storyteller-control-block storyteller-page-length">
      <label>
        Chapters to write
        <input
          aria-describedby="storyteller-chapter-count-hint"
          inputMode="numeric"
          max={plannedChaptersMax}
          min={1}
          step={1}
          type="number"
          value={draft ?? count}
          onBlur={() => setDraft(null)}
          onChange={(event) => {
            const text = event.currentTarget.value;
            // A number is kept as the count (settled into range, as shown); anything else stays as typed for now.
            if (text.trim() && Number.isFinite(Number(text))) {
              setCount(Number(text));
              setDraft(null);
            } else setDraft(text);
          }}
        />
      </label>
      <small id="storyteller-chapter-count-hint">{hint}</small>
    </div>
  );
}

export function StoryControls({
  providers,
  register,
  errors,
  premiseLength,
  createJobMutation,
  submitStatus,
  selectedTone,
  setSelectedTone,
  writingStyle,
  setWritingStyle,
  chapterChoice,
  pageLength,
  onGenerate,
  onAddChapter,
  handleSubmit,
  latestJob,
}: StoryControlsProps) {
  const { chapter, story } = chapterChoice;
  return (
    <aside className="storyteller-controls" aria-label="Story controls">
      <div className="storyteller-panel-heading">
        <div><p className="eyebrow">Story controls</p><h3>Guide the next passage</h3></div>
        <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
      </div>
      <form className="storyteller-form" onSubmit={handleSubmit(onGenerate)}>
        <label>
          Provider
          <select {...register('providerId')}>
            <option value="">Default LLM provider</option>
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}
          </select>
        </label>
        {story ? (
          // Generate adds to the open story; its title and premise are its own.
          <p className="storyteller-generate-target">
            Adds to <strong>{story.title.trim() || 'Untitled story'}</strong>: chapter {chapterChoice.lastChapter} goes on,
            chapter {chapterChoice.lastChapter + 1} starts a new one. Use New story draft for another story.
          </p>
        ) : (
          <>
            <label>Title<input {...register('title')} placeholder="Untitled story" /></label>
            <label>
              Premise <span aria-live="polite">{premiseLength}/{premiseMaxChars}</span>
              <textarea
                aria-invalid={Boolean(errors.premise)}
                placeholder="A young herbalist discovers a small secret that could change her quiet valley."
                maxLength={premiseMaxChars}
                rows={4}
                {...register('premise', { required: true, maxLength: premiseMaxChars })}
              />
            </label>
          </>
        )}
        <ToneChooser selectedTone={selectedTone} setSelectedTone={setSelectedTone} />
        <label>
          Writing style
          <select value={writingStyle} onChange={(event) => setWritingStyle(event.target.value)}>
            {[...new Set([...styleOptions, writingStyle])].map((style) => <option key={style} value={style}>{style}</option>)}
          </select>
        </label>
        {story ? (
          // Where Generate writes in the open story; reading another chapter is the Outline's job.
          <div className="storyteller-chapter-controls">
            <span>Write into chapter</span>
            <button aria-label="Previous chapter" type="button" disabled={chapter <= chapterChoice.min} onClick={() => chapterChoice.setChapter(chapter - 1)}>‹</button>
            <strong>{chapter}</strong>
            <button aria-label="Next chapter" type="button" disabled={chapter >= chapterChoice.max} onClick={() => chapterChoice.setChapter(chapter + 1)}>›</button>
            <button type="button" disabled={createJobMutation.isPending} onClick={onAddChapter}>New chapter</button>
          </div>
        ) : null}
        <ChapterCountField chapterChoice={chapterChoice} />
        <PageLengthField pageLength={pageLength} />
        <Button
          aria-label={createJobMutation.isPending ? 'Queueing story' : 'Queue story'}
          className="storyteller-generate"
          type="submit"
          disabled={createJobMutation.isPending}
          loading={createJobMutation.isPending}
        >
          {createJobMutation.isPending ? 'Generating story…' : 'Generate story'}
        </Button>
      </form>
      <FeatureValidationMessage show={Boolean(errors.premise)} message="Enter a premise before generating a story." />
      <FeatureSubmitFeedback
        error={createJobMutation.error}
        errorPrefix="Story request"
        isError={createJobMutation.isError}
        isPending={createJobMutation.isPending}
        jobId={createJobMutation.data?.job.id}
        pendingMessage="Generating story…"
        successPrefix={latestJob?.status === 'completed' ? 'Story generated' : 'Story job queued'}
      />
      <div className="storyteller-output-status">
        <div className="storyteller-panel-heading compact"><p className="eyebrow">Output status</p></div>
        {latestJob ? (
          <article className="storyteller-output-card">
            <div><strong>{latestJob.type}</strong><OmnixStatusPill>{latestJob.status}</OmnixStatusPill></div>
            <Progress value={jobProgressPercent(latestJob.progress)} aria-label={`${latestJob.type} progress`} />
            {/* A Generate of several chapters says which one it is writing. */}
            {latestJob.status === 'running' && latestJob.progress?.message ? <small>{latestJob.progress.message}</small> : null}
            <small>{latestJob.resource_class}</small>
            {jobOutputText(latestJob) ? <p>{truncate(jobOutputText(latestJob) ?? '', 180)}</p> : null}
          </article>
        ) : <div className="storyteller-empty-small">No generation yet.</div>}
      </div>
    </aside>
  );
}
