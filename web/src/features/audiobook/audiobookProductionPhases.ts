import { useEffect } from 'react';
import type { AudiobookWorkspaceModel } from './useAudiobookWorkspace';
import type { LibrarySection } from './audiobookWorkspaceModel';
import { extractQuotes, reclassifyAudiobook } from './audiobookWorkspaceModel';
import { audiobookApi } from './audiobookApi';
import type { ApprovalStep } from './audiobookTypes';
import { isJobActive } from '../../api/jobs';

// Project states once classification has finished, and once quote review is behind the book.
const CLASSIFIED_STATES = new Set(['review_required', 'ready_to_render', 'rendering', 'mastering', 'ready_to_export', 'exported']);
const PAST_QUOTE_REVIEW_STATES = new Set(['analyzing', ...CLASSIFIED_STATES]);

/** What to do while a phase is the current one: a sentence, and the button that does it (none while waiting). */
/** `reasoningChoice`: the button starts Find speakers, so the No reasoning box goes beside it. */
export type PhaseNextAction = { prompt: string; label?: string; run?: () => void; reasoningChoice?: boolean };

/** The listener's sign-off that ends a step and moves the book on; `blocked` says what must happen first. */
export type PhaseApproval = { label: string; run: () => void; blocked?: string; reasoningChoice?: boolean };

export type ProductionPhase = {
  title: string;
  /** What to do on the step's page, in a sentence or two. */
  detail: string;
  status: string;
  complete: boolean;
  /** Label of the button that opens the phase's page. */
  action: string;
  open: () => void;
  next: PhaseNextAction;
  /** Steps 2 to 5 end when the listener approves them; steps 1 and 6 end by doing them. */
  approve?: PhaseApproval;
};

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

/** The label of the button that starts speaker classification. */
export function findSpeakersLabel(ws: Pick<AudiobookWorkspaceModel, 'project' | 'reclassificationRunning'>): string {
  if (ws.reclassificationRunning) return 'Finding speakers…';
  return ws.project && PAST_QUOTE_REVIEW_STATES.has(ws.project.state) ? 'Find speakers again' : 'Approve quotes and find speakers';
}

/** The six production phases of the open project, from adding the book to exporting it. */
export function productionPhases(ws: AudiobookWorkspaceModel): ProductionPhase[] {
  const {
    action, assignedVoiceCount, canRender, castableSpeakers, classificationRules, completedRenderChapters,
    extractionRunning, failedRenderJobs, navigateLibrary, noReasoning, openManuscriptReview, openSourceUpload, pausedRenderJobs,
    project, queuedRenderJobs, reclassificationRunning, renderChapterCount, renderProgressPercent, rulesNeedExtraction,
    runningRenderJobs,
  } = ws;
  if (!project) return [];
  const rules = classificationRules[project.id] ?? project.classification_rules ?? '';
  const hasSource = Boolean(project.current_source_revision_id);
  const openSource = () => openSourceUpload(project.id);
  const go = (section: LibrarySection) => () => navigateLibrary(section);
  const openProduction = go('exports');
  const issues = project.review_issues.length;
  // Approving the quotes starts Find speakers, so quote review is done once the book has moved on to it (and the
  // rules have not changed since). Steps 3 to 5 are done once their work is finished and the listener approved
  // that result; the server clears an approval when the result changes.
  const quotesReviewed = hasSource && !extractionRunning && !rulesNeedExtraction && PAST_QUOTE_REVIEW_STATES.has(project.state);
  const speakersFound = quotesReviewed && !reclassificationRunning && CLASSIFIED_STATES.has(project.state) && issues === 0;
  const approved = (step: ApprovalStep) => project.step_approvals?.[step] ?? false;
  const textClassified = speakersFound && approved('speakers');
  const unassignedVoices = castableSpeakers.length - assignedVoiceCount;
  const voicesChosen = castableSpeakers.length > 0 && unassignedVoices === 0;
  const rendered = renderChapterCount > 0 && completedRenderChapters === renderChapterCount;
  const latestExport = project.export_jobs[0];
  const findSpeakers = () => void action(() => reclassifyAudiobook(project.id, rules, noReasoning), 'Finding speakers. This can take a while for a long book.');
  const approveQuotes = () => void action(async () => {
    await reclassifyAudiobook(project.id, rules, noReasoning);
    navigateLibrary('review');
  }, 'Quotes approved. Finding speakers; this can take a while for a long book.');
  const approve = (step: ApprovalStep, done: string, then?: LibrarySection) => () => void action(async () => {
    await audiobookApi.approveStep(project.id, step);
    if (then) navigateLibrary(then);
  }, done);
  const approveSpeakers = approve('speakers', 'Speakers approved. Next, choose a voice for each one.', 'characters');
  const approveCast = approve('cast', 'Cast approved. Next, render the audio.', 'exports');
  const approveAudio = approve('audio', 'Audio approved. Next, choose a format and export.');

  const quotesNext: PhaseNextAction = extractionRunning
    ? { prompt: 'Finding the quotes in your book. This can take a few minutes; the quotes appear when it finishes.' }
    : rulesNeedExtraction
      ? { prompt: 'Your quote rules changed. Extract the quotes again so the review uses the new rules.', label: 'Extract quotes',
        run: () => void action(() => extractQuotes(project.id, rules), 'Extracting quotes again. Review them when they appear.') }
      : { prompt: 'Read through the quotes found in your book. Fix any that are wrong and remove text that should not be read aloud. When they look right, approve them and Omnix finds who says each line.',
        label: 'Review quotes', run: openManuscriptReview };

  const speakersNext: PhaseNextAction = reclassificationRunning
    ? { prompt: 'Working out who says each line. This can take a while for a long book.' }
    : issues
      ? { prompt: `Omnix was not sure who says ${plural(issues, 'line')}. Confirm the speaker for each one.`, label: `Review ${plural(issues, 'line')}`, run: go('review') }
      : speakersFound
        ? { prompt: `Omnix found ${plural(project.speakers.length, 'speaker')}. Check who says what, then approve the speakers to move on to casting.`,
          label: 'Approve speakers', run: approveSpeakers }
        : { prompt: 'Find who says each line so every speaker can get their own voice.', label: 'Find speakers', run: findSpeakers, reasoningChoice: true };

  const castNext: PhaseNextAction = voicesChosen
    ? { prompt: 'Every speaker has a voice. Audition the cast, then approve it to move on to rendering.', label: 'Approve cast', run: approveCast }
    : castableSpeakers.length
    ? { prompt: `Choose a voice for ${unassignedVoices === castableSpeakers.length ? 'each speaker' : `the ${plural(unassignedVoices, 'speaker')} still without one`}. You can audition a voice before you choose it.`,
      label: 'Choose voices', run: go('characters') }
    : { prompt: 'No speakers were found. Find speakers again, or add a speaker on the Cast page.', label: 'Open cast', run: go('characters') };

  const blockers = project.render_readiness?.blockers.length ?? 0;
  const renderNext: PhaseNextAction = rendered
    ? { prompt: 'Every chapter is rendered. Listen to the chapters, then approve the audio to move on to export.', label: 'Approve audio', run: approveAudio }
    : failedRenderJobs
    ? { prompt: `${plural(failedRenderJobs, 'chapter')} failed to render.`, label: 'Retry failed chapters', run: openProduction }
    : pausedRenderJobs
      ? { prompt: `${plural(pausedRenderJobs, 'chapter')} paused.`, label: 'Resume rendering', run: openProduction }
      : runningRenderJobs + queuedRenderJobs
        ? { prompt: `Rendering the audio: ${completedRenderChapters} of ${plural(renderChapterCount, 'chapter')} done.`, label: 'View progress', run: openProduction }
        : canRender
          ? { prompt: 'Everything is ready. Play a sample to check the voices, then render the book.', label: 'Go to rendering', run: openProduction }
          : blockers
            ? { prompt: `${plural(blockers, 'thing')} must be fixed before the book can render.`, label: 'See what is left', run: openProduction }
            : { prompt: 'Finish the earlier steps first.' };

  const exportNext: PhaseNextAction = latestExport && ['failed', 'dead_letter'].includes(latestExport.status)
    ? { prompt: 'The last export failed.', label: 'Export again', run: openProduction }
    : latestExport && isJobActive(latestExport.status)
      ? { prompt: 'Exporting the audiobook.', label: 'View progress', run: openProduction }
      : project.state === 'ready_to_export'
        ? { prompt: 'Every chapter is rendered. Choose a format and export the audiobook.', label: 'Go to export', run: openProduction }
        : { prompt: 'Assembling the rendered chapters. Export becomes available when they are ready.', label: 'View progress', run: openProduction };

  return [
    { title: 'Add book', detail: 'Upload the book, or choose one from the local library. Omnix splits it into chapters and finds the quotes.', status: hasSource ? 'Book added' : 'No book yet', complete: hasSource,
      action: 'Open book source', open: openSource,
      next: { prompt: 'Upload the book you want to turn into an audiobook, or choose one from the local library.', label: 'Add a book', run: openSource } },
    { title: 'Review quotes', detail: 'Read each chapter and check the quotes Omnix found. Fix any that are wrong, remove text that should not be read aloud, then approve the quotes.',
      status: extractionRunning ? 'Extracting quotes' : rulesNeedExtraction ? 'Rules changed' : quotesReviewed ? 'Reviewed' : hasSource ? 'Ready to review' : 'Waiting for a book',
      complete: quotesReviewed, action: 'Open quotes', open: openManuscriptReview, next: quotesNext,
      approve: { label: 'Approve quotes', run: approveQuotes, reasoningChoice: true,
        blocked: !hasSource ? 'Add a book first.' : extractionRunning ? 'Wait for the quotes to be extracted.'
          : rulesNeedExtraction ? 'Your rules changed. Extract the quotes again first.' : undefined } },
    { title: 'Find speakers', detail: 'Omnix works out who says each line. Confirm the lines it was unsure about, check the speakers, then approve them.',
      status: reclassificationRunning ? 'Finding speakers' : !quotesReviewed ? 'After quote review' : issues ? `${plural(issues, 'line')} to confirm`
        : speakersFound && !textClassified ? 'Ready to approve' : `${plural(project.speakers.length, 'speaker')} found`,
      complete: textClassified, action: 'Open speaker review', open: go('review'), next: speakersNext,
      approve: { label: 'Approve speakers', run: approveSpeakers,
        blocked: reclassificationRunning ? 'Wait for Find speakers to finish.' : !quotesReviewed || !CLASSIFIED_STATES.has(project.state) ? 'Find speakers first.'
          : issues ? `Confirm the speaker for ${plural(issues, 'line')} first.` : undefined } },
    { title: 'Cast voices', detail: 'Pick a voice for every speaker and audition it on lines from the book. When the cast sounds right, approve it.',
      status: voicesChosen && !approved('cast') ? 'Ready to approve' : `${assignedVoiceCount} / ${castableSpeakers.length} voices chosen`,
      complete: voicesChosen && approved('cast'), action: 'Open cast', open: go('characters'), next: castNext,
      approve: { label: 'Approve cast', run: approveCast,
        blocked: !castableSpeakers.length ? 'There are no speakers to cast yet.' : unassignedVoices ? `Choose a voice for ${plural(unassignedVoices, 'more speaker')} first.` : undefined } },
    { title: 'Render audio', detail: 'Play a sample, then render every chapter. Listen to the chapters and approve the audio when it sounds right.', status: rendered && !approved('audio') ? 'Ready to approve' : `${renderProgressPercent}% rendered`,
      complete: rendered && approved('audio'), action: 'Open rendering', open: openProduction, next: renderNext,
      approve: { label: 'Approve audio', run: approveAudio, blocked: rendered ? undefined : 'Render every chapter first.' } },
    { title: 'Export', detail: 'Choose a format and export the finished audiobook. The file appears in Assets to download.', status: project.state === 'exported' ? 'Exported' : project.state === 'ready_to_export' ? 'Ready to export' : 'After rendering',
      complete: project.state === 'exported', action: 'Open export', open: openProduction, next: exportNext },
  ];
}

/** The index of the first unfinished phase, or -1 once every phase is complete. */
export function currentPhaseIndex(phases: ProductionPhase[]): number {
  return phases.findIndex((phase) => !phase.complete);
}

/** The page where a phase's work is done; past the last phase, the export page. */
export function sectionForPhase(index: number): LibrarySection {
  if (index === 2) return 'review';
  if (index === 3) return 'characters';
  return index >= 4 || index < 0 ? 'exports' : 'projects';
}

/** A project waiting to land (just opened, or loaded from the URL) shows its current step's page once its detail arrives. */
export function useLandOnCurrentStep(ws: AudiobookWorkspaceModel): void {
  const { landingProjectId, project, setLandingProjectId, setLibrarySection, setWorkspaceMode } = ws;
  const section = landingProjectId && project?.id === landingProjectId
    ? sectionForPhase(currentPhaseIndex(productionPhases(ws))) : null;
  useEffect(() => {
    if (!section) return;
    setLandingProjectId(null);
    setLibrarySection(section);
    setWorkspaceMode(section === 'exports' ? 'production' : 'review');
  }, [section, setLandingProjectId, setLibrarySection, setWorkspaceMode]);
}

/** The production phase a project page belongs to, or null for pages outside the path. */
export function phaseIndexForSection(section: LibrarySection, phases: ProductionPhase[]): number | null {
  switch (section) {
    case 'projects': case 'pronunciations': return 1;
    case 'review': return 2;
    case 'characters': case 'voices': return 3;
    case 'exports': return phases[4]?.complete ? 5 : 4;
    default: return null;
  }
}
