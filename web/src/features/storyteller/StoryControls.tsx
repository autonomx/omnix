/** The draft controls: provider, title, premise, tone, style and chapter. */
import { Button, Progress } from '@mantine/core';
import { type UseMutationResult } from '@tanstack/react-query';
import { type FieldErrors, type UseFormHandleSubmit, type UseFormRegister } from 'react-hook-form';
import { type JobRecord } from '../../api/client';
import { OmnixStatusPill } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../../shared/FeatureSubmitFeedback';
import { jobProgressPercent } from '../../api/jobProgress';
import { jobOutputText, premiseMaxChars, StoryGenerationRequest, StoryGenerationResult, StorytellerFormValues, styleOptions, toneOptions, truncate } from './storyModel';

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
  selectedChapter: number;
  setSelectedChapter: (chapter: number) => void;
  onGenerate: (values: StorytellerFormValues) => void;
  onAddChapter: () => void;
  handleSubmit: UseFormHandleSubmit<StorytellerFormValues>;
  latestJob: JobRecord | null;
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
  selectedChapter,
  setSelectedChapter,
  onGenerate,
  onAddChapter,
  handleSubmit,
  latestJob,
}: StoryControlsProps) {
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
        <div className="storyteller-control-block">
          <span>Tone & mood</span>
          <div className="storyteller-chip-row">
            {/* A preset's own tone or style is offered alongside the usual ones (ST-5.2). */}
            {[...new Set([...toneOptions, selectedTone])].map((tone) => (
              <button className={tone === selectedTone ? 'active' : ''} key={tone} type="button" onClick={() => setSelectedTone(tone)}>{tone}</button>
            ))}
          </div>
        </div>
        <label>
          Writing style
          <select value={writingStyle} onChange={(event) => setWritingStyle(event.target.value)}>
            {[...new Set([...styleOptions, writingStyle])].map((style) => <option key={style} value={style}>{style}</option>)}
          </select>
        </label>
        <div className="storyteller-chapter-controls">
          <span>Chapter</span>
          <button type="button" onClick={() => setSelectedChapter(Math.max(1, selectedChapter - 1))}>‹</button>
          <strong>{selectedChapter}</strong>
          <button type="button" onClick={() => setSelectedChapter(selectedChapter + 1)}>›</button>
          <button type="button" disabled={createJobMutation.isPending} onClick={onAddChapter}>New chapter</button>
        </div>
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
            <small>{latestJob.resource_class}</small>
            {jobOutputText(latestJob) ? <p>{truncate(jobOutputText(latestJob) ?? '', 180)}</p> : null}
          </article>
        ) : <div className="storyteller-empty-small">No generation yet.</div>}
      </div>
    </aside>
  );
}
