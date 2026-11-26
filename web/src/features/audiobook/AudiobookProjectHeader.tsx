import { LibrarySection, base, extractQuotes, formatCount, formatDuration, importLibrarySource, saveClassificationRules, setAudiobookReadingMode, sourceAccept, updateProjectMetadata, uploadCover, uploadSource } from './audiobookWorkspaceModel';
import { useState, type ReactNode } from 'react';
import { NoReasoningOption } from './AudiobookReasoningOption';
import { currentPhaseIndex, productionPhases, type ProductionPhase } from './audiobookProductionPhases';
import type { AudiobookJobView } from './audiobookTypes';
import type { AudiobookWorkspaceModel } from './useAudiobookWorkspace';

const EXTRACTING_STATUSES = new Set(['queued', 'waiting', 'retrying', 'leased', 'running']);
const FAILED_STATUSES = new Set(['failed', 'dead_letter', 'stale']);

/** The extraction to show: one that is running, else the newest still waiting. */
function activeExtraction(jobs: AudiobookJobView[] | undefined): AudiobookJobView | undefined {
  const ingests = (jobs ?? []).filter((job) => job.type === 'audiobook.ingest');
  return ingests.find((job) => job.status === 'running' || job.status === 'leased')
    ?? ingests.find((job) => EXTRACTING_STATUSES.has(job.status));
}

/** What the book source is doing right now: the upload, then the server's chapter extraction. */
function SourceProgress({ uploadingName, extraction, failed }: { uploadingName: string | null; extraction?: AudiobookJobView; failed?: AudiobookJobView }) {
  if (uploadingName) {
    return <div className="audiobook-source-progress" role="status" aria-live="polite">
      <span>Uploading {uploadingName}…</span>
      <progress aria-label="Book upload progress" max={100} />
    </div>;
  }
  if (extraction) {
    const started = extraction.status === 'running' || extraction.status === 'leased';
    const total = Number(extraction.progress?.total);
    const current = Number(extraction.progress?.current);
    const percent = started && total > 0 && Number.isFinite(current) ? Math.round((current / total) * 100) : null;
    return <div className="audiobook-source-progress" role="status" aria-live="polite">
      <span>{started ? `Extracting chapters · ${extraction.progress?.message || 'starting'}` : 'Book received · waiting to extract chapters'}</span>
      <progress aria-label="Chapter extraction progress" max={100} {...(percent === null ? {} : { value: percent })} />
      <small>Large books can take a few minutes. The book appears here when extraction finishes.</small>
    </div>;
  }
  if (failed) {
    return <p className="audiobook-source-progress error" role="alert">Chapter extraction failed{failed.error?.message ? `: ${failed.error.message}` : '.'} Upload the book again to retry.</p>;
  }
  return null;
}

/** The one thing to do next, then the six steps at a glance: done, current, or waiting on an earlier step. */
function ProductionPath({ phases, onOpenAssets, reasoningOption }: { phases: ProductionPhase[]; onOpenAssets: () => void; reasoningOption: ReactNode }) {
  const current = currentPhaseIndex(phases);
  const step = current >= 0 ? phases[current] : null;
  return (
    <section className="audiobook-production-flow" aria-label="Production path">
      <div className={`audiobook-next-step${step ? '' : ' done'}`} role="group" aria-label="Next step">
        <div className="audiobook-next-step-copy">
          <p className="eyebrow">{step ? `Next step · ${current + 1} of ${phases.length}` : 'All steps done'}</p>
          <h2 id="audiobook-next-step-title">{step ? step.title : 'Your audiobook is exported'}</h2>
          <p>{step ? step.next.prompt : 'Download it from Assets, or export another format from Render & Export.'}</p>
        </div>
        {step
          ? step.next.label && step.next.run && (step.next.reasoningChoice
            ? <div className="audiobook-next-step-actions"><button type="button" className="audiobook-primary-action" onClick={step.next.run}>{step.next.label}</button>{reasoningOption}</div>
            : <button type="button" className="audiobook-primary-action" onClick={step.next.run}>{step.next.label}</button>)
          : <button type="button" className="audiobook-primary-action" onClick={onOpenAssets}>Open Assets</button>}
      </div>
      <ol className="audiobook-production-flow-steps" aria-label="Audiobook production steps">
        {phases.map((phase, index) => {
          const state = phase.complete ? 'complete' : index === current ? 'current' : 'upcoming';
          return <li key={phase.title} className={state} aria-current={index === current ? 'step' : undefined}>
            <span className="audiobook-production-flow-number" aria-hidden="true">{phase.complete ? '✓' : index + 1}</span>
            <div className="audiobook-production-flow-copy"><strong>{phase.title}</strong><small>{phase.status}</small></div>
            {phase.complete
              ? <button type="button" onClick={phase.open}>{phase.action}</button>
              : <span className="audiobook-production-flow-status">{index === current ? 'You are here' : `Finish step ${current + 1} first`}</span>}
          </li>;
        })}
      </ol>
    </section>
  );
}

/** The open project's header, production path and settings. */
export function AudiobookProjectHeader({ ws }: { ws: AudiobookWorkspaceModel }) {
  const {
    action, assignedVoiceCount, busy, classificationRules, completedRenderChapters, excludePageRanges, extractionRunning,
    librarySection, navigateLibrary, openSourceLibrary, project, projectAuthor, projectSettingsOpen, projectTitle,
    queueSamplePreview, reclassificationRunning, renderChapterCount, rulesNeedExtraction, setClassificationRules,
    setDeleteConfirmationOpen, setExcludePageRanges, setProjectAuthor, setProjectSettingsOpen, setProjectTitle,
    setSourceLibraryFilename, setSourceLibraryOpen, sourceLibraryFilename, sourceLibraryOpen, sourceLibraryQuery,
  } = ws;
  const [uploadingName, setUploadingName] = useState<string | null>(null);
  if (!project) return null;
  const extraction = activeExtraction(project.pipeline_jobs);
  const newestIngest = project.pipeline_jobs?.find((job) => job.type === 'audiobook.ingest');
  const failedExtraction = !project.current_source_revision_id && newestIngest && FAILED_STATUSES.has(newestIngest.status) ? newestIngest : undefined;
  const sourceBusy = Boolean(uploadingName || extraction);
  const sourceState = uploadingName ? 'Uploading' : extraction ? 'Extracting' : project.current_source_revision_id ? 'Source attached' : 'Source needed';
  const phases = productionPhases(ws);
  const current = currentPhaseIndex(phases);
  const stepsDone = phases.filter((phase) => phase.complete).length;
  const stepsPercent = phases.length ? Math.round((stepsDone / phases.length) * 100) : 0;
  const rules = classificationRules[project.id] ?? project.classification_rules ?? '';
  return (
    <>
      <nav className="audiobook-breadcrumb" aria-label="Audiobook breadcrumb"><button type="button" onClick={() => navigateLibrary('projects')}>Audiobook</button><span>›</span><strong>{project.title}</strong>{librarySection !== 'projects' && <><span>›</span><strong>{({ library: 'Library', books: 'Books', chapters: 'Chapters', assets: 'Assets', documents: 'Documents', characters: 'Cast & Voice Tools', voices: 'Voices', pronunciations: 'Pronunciations', exports: 'Render & Export', projects: 'Projects' } as Record<LibrarySection, string>)[librarySection]}</strong></>}</nav>
      <header className="audiobook-card audiobook-project-header" id="audiobook-book">
        <div className="audiobook-project-overview">
          {project.cover_asset_id && <img className="audiobook-cover" src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt={`Cover of ${project.title}`} />}
          <div className="audiobook-header-copy"><p className="eyebrow">Audiobook project · {project.state.replaceAll('_', ' ')}</p><h1>{project.title}</h1><p>A local-first audiobook production workspace.</p>
            <div className="audiobook-tag-row">{project.source_format && <span>{project.source_format.toUpperCase()} source</span>}<span>{project.chapters.length} chapters</span></div>
            <p className="audiobook-project-stats"><span className="audiobook-project-stats-sentence">{formatCount(project.word_count)} words</span><strong>{formatCount(project.word_count)}</strong><small>WORDS</small><strong>{project.chapters.length}</strong><small>CHAPTERS</small><strong>{project.speakers.length}</strong><small>SPEAKERS</small><strong>{formatDuration(project.estimated_runtime_seconds)}</strong><small>EST. RUNTIME</small></p>
          </div>
        </div>
        <div className="audiobook-project-header-side">
          <div className="audiobook-header-action-buttons"><button type="button" aria-expanded={projectSettingsOpen} onClick={() => setProjectSettingsOpen((open) => !open)}>{projectSettingsOpen ? 'Close editor' : 'Edit project'}</button><button type="button" className={assignedVoiceCount > 0 ? 'audiobook-primary-action' : undefined} disabled={busy} title={assignedVoiceCount > 0 ? 'Hear a short passage with the chosen voices' : 'Choose a voice in step 4 to hear the cast'} onClick={queueSamplePreview}>Play sample</button><button type="button" aria-label="More project actions" onClick={() => setProjectSettingsOpen(true)}>...</button></div>
          <div className={`audiobook-status-meter${project.review_issues.length ? ' has-issues' : ''}`}><div><p className="eyebrow">Progress</p><strong>{`${stepsDone} of ${phases.length} steps done`}</strong>{project.review_issues.length
            ? <button type="button" className="audiobook-status-issues" onClick={() => navigateLibrary('review')}>{project.review_issues.length} issues to resolve</button>
            : <span>{current < 0 ? 'Audiobook exported' : current === 4 ? `${completedRenderChapters} / ${renderChapterCount} chapters rendered` : `Now: ${phases[current].title}`}</span>}</div><b>{stepsPercent}%</b><progress aria-label="Steps done" max={100} value={stepsPercent} /></div>
        </div>
        <ProductionPath phases={phases} onOpenAssets={() => navigateLibrary('assets')} reasoningOption={<NoReasoningOption ws={ws} />} />
        {projectSettingsOpen && <div className="audiobook-project-actions">
          <section className="audiobook-settings-card audiobook-source-settings" aria-labelledby="audiobook-source-settings-title">
            <div className="audiobook-settings-heading"><div><p className="eyebrow">Step 1: Add book</p><h2 id="audiobook-source-settings-title" tabIndex={-1}>Book source</h2></div><span className={`audiobook-source-state ${sourceBusy ? 'working' : project.current_source_revision_id ? 'attached' : 'needed'}`}>{sourceState}</span></div>
            <p className="audiobook-source-filename">{project.source_filename || uploadingName || (extraction ? 'Book received' : 'No book uploaded yet')}</p>
            <p className="audiobook-settings-description">Upload a PDF, EPUB, DOCX, Markdown, HTML, or text file to extract chapters.</p>
            <SourceProgress uploadingName={uploadingName} extraction={extraction} failed={failedExtraction} />
            <div className="audiobook-source-actions">
              <label className={`audiobook-source-file-button${busy || sourceBusy ? ' disabled' : ''}`}><span>Upload from computer</span>
                <input type="file" accept={sourceAccept} disabled={busy || sourceBusy}
                  onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (!file) return; setUploadingName(file.name); void action(async () => { await uploadSource(project.id, file, excludePageRanges, classificationRules[project.id] ?? project.classification_rules ?? ''); setExcludePageRanges(''); }, 'Book uploaded. Extracting chapters now.').finally(() => setUploadingName(null)); }} />
              </label>
              <button type="button" className="audiobook-source-library-trigger" disabled={busy || sourceBusy} onClick={openSourceLibrary}>Choose from local library</button>
            </div>
            <details className="audiobook-source-library" open={sourceLibraryOpen} onToggle={(event) => {
              setSourceLibraryOpen(event.currentTarget.open);
              if (event.currentTarget.open && !sourceLibraryQuery.data) void sourceLibraryQuery.refetch();
            }}>
              <summary>Browse resources\data\audiobooks</summary>
              <p className="audiobook-hint">Choose a book already stored in the local audiobook folder.</p>
              {sourceLibraryQuery.isFetching && <p role="status">Loading local books…</p>}
              {sourceLibraryQuery.isError && <p role="alert">Could not read the local audiobook folder.</p>}
              {sourceLibraryQuery.data && !sourceLibraryQuery.data.files.length && <p role="status">No supported books found in this folder.</p>}
              {sourceLibraryQuery.data && sourceLibraryQuery.data.files.length > 0 && <>
                <label>Source book<select aria-label="Local audiobook source" value={sourceLibraryFilename}
                  onChange={(event) => setSourceLibraryFilename(event.target.value)} disabled={busy}>
                  <option value="">Choose a source book</option>
                  {sourceLibraryQuery.data.files.map((file) => <option key={file.name} value={file.name}>{file.name}</option>)}
                </select></label>
                <button type="button" disabled={busy || !sourceLibraryFilename}
                  onClick={() => void action(async () => { await importLibrarySource(project.id, sourceLibraryFilename, excludePageRanges, classificationRules[project.id] ?? project.classification_rules ?? ''); setExcludePageRanges(''); }, 'Source queued for extraction.')}>Use selected book</button>
              </>}
            </details>
            <details className="audiobook-source-advanced"><summary>PDF page options</summary>
              <label className="audiobook-page-filter">Exclude pages
                <input aria-label="Exclude PDF pages" inputMode="text" placeholder="e.g. 1-3, 42-45"
                  value={excludePageRanges} onChange={(event) => setExcludePageRanges(event.target.value)} disabled={busy} />
                <small>Enter 1-based page numbers. Applied when the next PDF source is uploaded.</small>
              </label>
            </details>
            <label className="audiobook-classification-rules">Quote and speaker rules (optional)
              <textarea value={rules} maxLength={4000} rows={3}
                disabled={busy || reclassificationRunning}
                onChange={(event) => setClassificationRules((previous) => ({ ...previous, [project.id]: event.target.value }))}
                placeholder="Character quotes can also be in speaker: quote format." aria-describedby="audiobook-rules-help" />
            </label>
            <small id="audiobook-rules-help" className="audiobook-rules-help">Tell Omnix how this book marks its quotes and speakers.</small>
            <button type="button" disabled={busy || reclassificationRunning}
              onClick={() => void action(() => saveClassificationRules(project.id, rules), 'Rules saved. They apply the next time quotes are extracted or speakers are found.')}>Save rules</button>
            <div className={`audiobook-source-reclassify${rulesNeedExtraction ? ' needs-action' : ''}`}>
              <p>{rulesNeedExtraction
                ? 'Rules changed. Extract the quotes again, then review them before finding speakers.'
                : 'Changing the rules? Extract the quotes again to apply them, then review the quotes.'}</p>
              <button type="button" disabled={busy || extractionRunning || reclassificationRunning || !project.current_source_revision_id}
                onClick={() => void action(() => extractQuotes(project.id, rules), 'Extracting quotes again. Review them when they appear.')}>
                {extractionRunning ? 'Extracting quotes…' : 'Extract quotes again'}
              </button>
            </div>
          </section>
          <div className="audiobook-settings-side">
            <section className="audiobook-settings-card" aria-labelledby="audiobook-details-settings-title">
              <div className="audiobook-settings-heading"><div><p className="eyebrow">Project</p><h2 id="audiobook-details-settings-title">Details &amp; reading</h2></div></div>
              <div className="audiobook-settings-fields"><label>Title<input value={projectTitle} onChange={(event) => setProjectTitle(event.target.value)} /></label>
                <label>Author<input value={projectAuthor} onChange={(event) => setProjectAuthor(event.target.value)} /></label></div>
              <label className="audiobook-reading-mode">Audiobook reading mode
                <select aria-label="Audiobook reading mode" value={project.audiobook_mode ?? 'standard'} disabled={busy}
                  onChange={(event) => { const mode = event.target.value as 'standard' | 'story_only' | 'verbatim'; void action(() => setAudiobookReadingMode(project.id, mode), `Reading mode changed to ${mode.replaceAll('_', ' ')}.`); }}>
                  <option value="standard">Standard audiobook</option><option value="story_only">Story only</option><option value="verbatim">Verbatim source</option>
                </select>
                <small>{(project.audiobook_mode ?? 'standard') === 'story_only'
                  ? 'Reads the story and scene headings while skipping front matter, page numbers, and publishing details.'
                  : (project.audiobook_mode ?? 'standard') === 'verbatim'
                    ? 'Reads every extracted block, including headings and publishing details.'
                    : 'Reads story and chapter structure while skipping contents pages and running headers.'}</small>
              </label>
              <button type="button" className="audiobook-settings-save" disabled={busy || !projectTitle.trim() || (projectTitle === project.title && projectAuthor === project.author)}
                onClick={() => void action(() => updateProjectMetadata(project.id, projectTitle.trim(), projectAuthor.trim()), 'Project metadata saved. Export metadata will use the new values.')}>Save details</button>
            </section>
            <section className="audiobook-settings-card audiobook-cover-settings" aria-labelledby="audiobook-cover-settings-title">
              <div className="audiobook-settings-heading"><div><p className="eyebrow">Artwork</p><h2 id="audiobook-cover-settings-title">Book cover</h2></div></div>
              <p className="audiobook-settings-description">{project.cover_asset_id ? 'Cover added. Upload a new image to replace it.' : 'Add a cover image for your audiobook.'}</p>
              <label className="audiobook-source-file-button audiobook-cover-file-button"><span>{project.cover_asset_id ? 'Replace cover' : 'Choose cover image'}</span>
                <input type="file" accept="image/jpeg,image/png" disabled={busy}
                  onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void action(() => uploadCover(project.id, file), 'Cover saved for future exports.'); event.currentTarget.value = ''; }} />
              </label>
            </section>
            <section className="audiobook-settings-card audiobook-danger-settings" aria-labelledby="audiobook-danger-settings-title">
              <div><p className="eyebrow">Danger zone</p><h2 id="audiobook-danger-settings-title">Delete project</h2></div>
              <button type="button" className="audiobook-danger-action" disabled={busy} onClick={() => setDeleteConfirmationOpen(true)}>Delete audiobook</button>
            </section>
          </div>
        </div>}
      </header>
    </>
  );
}
