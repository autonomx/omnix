import { LibrarySection, base, extractQuotes, formatCount, formatDuration, importLibrarySource, reclassifyAudiobook, saveClassificationRules, setAudiobookReadingMode, sourceAccept, updateProjectMetadata, uploadCover, uploadSource } from './audiobookWorkspaceModel';
import type { AudiobookWorkspaceModel } from './useAudiobookWorkspace';

/** The open project's header, production path and settings. */
export function AudiobookProjectHeader({ ws }: { ws: AudiobookWorkspaceModel }) {
  const {
    action, assignedVoiceCount, busy, castableSpeakers, classificationRules, completedRenderChapters,
    excludePageRanges, extractionRunning, librarySection, navigateLibrary, openManuscriptReview, openSourceLibrary,
    openSourceUpload, project, projectAuthor, projectSettingsOpen, projectTitle, queueSamplePreview,
    reclassificationRunning, renderChapterCount, renderProgressPercent, rulesNeedExtraction, setClassificationRules,
    setDeleteConfirmationOpen, setExcludePageRanges, setProjectAuthor, setProjectSettingsOpen, setProjectTitle,
    setSourceLibraryFilename, setSourceLibraryOpen, sourceLibraryFilename, sourceLibraryOpen, sourceLibraryQuery,
  } = ws;
  if (!project) return null;
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
          <div className="audiobook-header-action-buttons"><button type="button" aria-expanded={projectSettingsOpen} onClick={() => setProjectSettingsOpen((open) => !open)}>{projectSettingsOpen ? 'Close editor' : 'Edit project'}</button><button type="button" className="audiobook-primary-action" disabled={busy} onClick={queueSamplePreview}>Play sample</button><button type="button" aria-label="More project actions" onClick={() => setProjectSettingsOpen(true)}>...</button></div>
          <div className="audiobook-status-meter"><div><p className="eyebrow">Project status</p><strong>{project.review_issues.length ? 'Review required' : project.state.replaceAll('_', ' ')}</strong><span>{project.review_issues.length ? `${project.review_issues.length} issues to resolve` : `${completedRenderChapters} / ${renderChapterCount} audiobook chapters rendered`}</span></div><b>{renderProgressPercent}%</b><progress max={100} value={renderProgressPercent} /></div>
        </div>
        <section className="audiobook-production-flow" aria-labelledby="audiobook-production-flow-title">
          <div className="audiobook-production-flow-heading"><div><p className="eyebrow">Production path</p><h2 id="audiobook-production-flow-title">From manuscript to audiobook</h2></div><p>Follow these steps in order. Open any step to continue your work.</p></div>
          <ol className="audiobook-production-flow-steps" aria-label="Audiobook production steps">
            {[
              { title: 'Add book', detail: 'Upload or choose a book; set title, author, and reading mode.', status: project.current_source_revision_id ? 'Source attached' : 'Source needed', complete: Boolean(project.current_source_revision_id), action: 'Open source', open: () => openSourceUpload(project.id) },
              { title: 'Extract quotes', detail: 'Detect quote spans, then review them and remove unwanted spoken text.', status: extractionRunning ? 'Extracting quotes' : project.current_source_revision_id ? 'Ready for quote review' : 'Add a book first', complete: false, action: 'Review spans', open: openManuscriptReview },
              { title: 'Classify text', detail: 'Review quote spans first. Start classification yourself to assign speakers.', status: reclassificationRunning ? 'Classifying' : project.state === 'extracted' ? 'Waiting for quote review' : project.review_issues.length ? `${project.review_issues.length} issues to review` : `${project.speakers.length} speakers found`, complete: false, action: 'Review speakers', open: openManuscriptReview },
              { title: 'Cast and direct', detail: 'Assign voices and adjust the delivery or emotion of dialogue.', status: `${assignedVoiceCount} / ${castableSpeakers.length} voices assigned`, complete: castableSpeakers.length > 0 && assignedVoiceCount === castableSpeakers.length, action: 'Manage cast', open: () => navigateLibrary('characters') },
              { title: 'Preview and render', detail: 'Listen to a sample, then generate the chapter audio.', status: `${renderProgressPercent}% rendered`, complete: renderChapterCount > 0 && completedRenderChapters === renderChapterCount, action: 'Open render', open: () => navigateLibrary('exports') },
              { title: 'Export', detail: 'Choose a format and download the finished audiobook.', status: project.state === 'exported' ? 'Exported' : ['ready_to_export', 'exported'].includes(project.state) ? 'Ready to export' : 'After rendering', complete: project.state === 'exported', action: 'Open exports', open: () => navigateLibrary('exports') },
            ].map((step, index) => <li key={step.title} className={step.complete ? 'complete' : ''}>
              <span className="audiobook-production-flow-number" aria-hidden="true">{index + 1}</span>
              <div className="audiobook-production-flow-copy"><strong>{step.title}</strong><small>{step.detail}</small></div>
              <span className="audiobook-production-flow-status">{step.status}</span>
              <button type="button" onClick={step.open}>{step.action}</button>
            </li>)}
          </ol>
        </section>
        {projectSettingsOpen && <div className="audiobook-project-actions">
          <section className="audiobook-settings-card audiobook-source-settings" aria-labelledby="audiobook-source-settings-title">
            <div className="audiobook-settings-heading"><div><p className="eyebrow">Phase 1: Add book</p><h2 id="audiobook-source-settings-title" tabIndex={-1}>Book source</h2></div><span className={`audiobook-source-state ${project.current_source_revision_id ? 'attached' : 'needed'}`}>{project.current_source_revision_id ? 'Source attached' : 'Source needed'}</span></div>
            <p className="audiobook-source-filename">{project.source_filename || 'No book uploaded yet'}</p>
            <p className="audiobook-settings-description">Upload a PDF, EPUB, DOCX, Markdown, HTML, or text file to extract chapters.</p>
            <div className="audiobook-source-actions">
              <label className="audiobook-source-file-button"><span>Upload from computer</span>
                <input type="file" accept={sourceAccept} disabled={busy}
                  onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void action(async () => { await uploadSource(project.id, file, excludePageRanges, classificationRules[project.id] ?? project.classification_rules ?? ''); setExcludePageRanges(''); }, 'Source queued for extraction.'); event.currentTarget.value = ''; }} />
              </label>
              <button type="button" className="audiobook-source-library-trigger" disabled={busy} onClick={openSourceLibrary}>Choose from local library</button>
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
            <label className="audiobook-classification-rules">Custom rules for classification (optional)
              <textarea value={classificationRules[project.id] ?? project.classification_rules ?? ''} maxLength={4000} rows={3}
                disabled={busy || reclassificationRunning}
                onChange={(event) => setClassificationRules((current) => ({ ...current, [project.id]: event.target.value }))}
                placeholder="Character quotes can also be in speaker: quote format." />
            </label>
            <button type="button" disabled={busy || reclassificationRunning}
              onClick={() => void action(() => saveClassificationRules(project.id, classificationRules[project.id] ?? project.classification_rules ?? ''), 'Classification rules saved. They apply to the next import or classification run.')}>Save classification rules</button>
            <div className="audiobook-source-reclassify"><div><strong>Phase 2: Extract quotes</strong><p>Extract quote spans using the rules above, then review the spans. Classification does not start automatically.</p></div>
              <button type="button" disabled={busy || extractionRunning || reclassificationRunning || !project.current_source_revision_id}
                onClick={() => void action(() => extractQuotes(project.id, classificationRules[project.id] ?? project.classification_rules ?? ''), 'Quote extraction queued. Review quote spans before classifying text.')}>
                {extractionRunning ? 'Extracting quotes…' : 'Extract quotes'}
              </button>
            </div>
            <div className="audiobook-source-reclassify"><div><strong>Phase 3: Classify text</strong><p>Review the extracted quote spans first, including unwanted text, then classify text to assign speakers.</p>
              {rulesNeedExtraction && <p>Rules changed. Extract quotes again and review the new spans before classifying.</p>}</div>
              <button type="button" disabled={busy || extractionRunning || reclassificationRunning || rulesNeedExtraction || !project.current_source_revision_id}
                onClick={() => void action(() => reclassifyAudiobook(project.id, classificationRules[project.id] ?? project.classification_rules ?? ''), 'Text classification queued.')}>
                {reclassificationRunning ? 'Classifying…' : 'Classify text'}
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
