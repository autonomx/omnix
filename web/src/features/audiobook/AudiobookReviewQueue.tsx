import { useEffect, useMemo, useRef, useState } from 'react';
import { audiobookApi } from './audiobookApi';
import type { ReviewIssue } from './audiobookTypes';
import type { AudiobookWorkspaceModel } from './useAudiobookWorkspace';

const REASON_LABELS: Record<string, string> = {
  UNSUPPORTED_SPEAKER: 'Speaker not in the cast',
  LOW_CONFIDENCE_SPEAKER: 'Low-confidence speaker',
  AMBIGUOUS_SPEAKER_IDENTITY: 'Ambiguous speaker',
  ATTRIBUTION_CONTRADICTION: 'Contradictory attribution',
  FALLBACK_NARRATOR: 'Fell back to the narrator',
  NARRATOR_DIALOGUE_UNCERTAIN: 'Narration or dialogue unclear',
  POSSIBLE_MISSED_DIALOGUE: 'Possible missed dialogue',
  STRUCTURE_UNCERTAIN: 'Structure unclear',
  AI_VERIFICATION_UNAVAILABLE: 'AI check unavailable',
};

export function reviewReasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason.toLowerCase().replaceAll('_', ' ');
}

function issueText(issue: ReviewIssue): string {
  return issue.reason === 'POSSIBLE_MISSED_DIALOGUE' && typeof issue.evidence?.excerpt === 'string' ? issue.evidence.excerpt : issue.source_text;
}

const sameName = (left: string, right: string) => left.trim().replace(/\s+/g, ' ').toLowerCase() === right.trim().replace(/\s+/g, ' ').toLowerCase();

/** Every open review issue in the main view, grouped by chapter, with the decisions that resolve them. */
export function AudiobookReviewQueue({ ws }: { ws: AudiobookWorkspaceModel }) {
  const { action, busy, librarySection, navigateLibrary, project, reviewSpeakers, setChapterId, setReviewSpeakers, setSelectedSpanId, workspaceMode } = ws;
  const [chapterFilter, setChapterFilter] = useState('all');
  const [reasonFilter, setReasonFilter] = useState('all');
  const [search, setSearch] = useState('');
  const sectionRef = useRef<HTMLElement>(null);
  const issues = useMemo(() => project?.review_issues ?? [], [project?.review_issues]);
  const reasons = useMemo(() => [...new Set(issues.map((issue) => issue.reason))].sort((left, right) => reviewReasonLabel(left).localeCompare(reviewReasonLabel(right))), [issues]);
  const groups = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const shown = issues.filter((issue) => (chapterFilter === 'all' || issue.chapter_id === chapterFilter)
      && (reasonFilter === 'all' || issue.reason === reasonFilter)
      && (!needle || `${issueText(issue)} ${issue.speaker_candidate ?? ''}`.toLowerCase().includes(needle)));
    return (project?.chapters ?? [])
      .map((chapter) => ({ chapter, issues: shown.filter((issue) => issue.chapter_id === chapter.id) }))
      .filter((group) => group.issues.length > 0);
  }, [chapterFilter, issues, project?.chapters, reasonFilter, search]);

  const open = Boolean(project) && workspaceMode === 'review' && librarySection === 'review';
  // Opened from a button further down the page: bring the queue's top into view.
  useEffect(() => {
    if (open) sectionRef.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  }, [open]);

  if (!project || !open) return null;
  const shownCount = groups.reduce((total, group) => total + group.issues.length, 0);
  const chaptersWithIssues = new Set(issues.map((issue) => issue.chapter_id)).size;
  const activeSpeakers = project.speakers.filter((speaker) => speaker.status === 'active');
  const chosenSpeaker = (issue: ReviewIssue) => reviewSpeakers[issue.id] ?? issue.speaker_id ?? '';
  // Only an issue whose chosen speaker is in the cast can be resolved; the rest wait for a decision.
  const confirmable = groups.flatMap((group) => group.issues).filter((issue) => activeSpeakers.some((speaker) => speaker.id === chosenSpeaker(issue)));
  const unconfirmable = shownCount - confirmable.length;
  const projectId = project.id;
  /** Confirms each shown issue's chosen speaker in turn; any confirmed before a failure stay confirmed. */
  const confirmAll = () => void action(async () => {
    for (const issue of confirmable) {
      await audiobookApi.resolveReview(projectId, issue.id, { speaker_id: chosenSpeaker(issue), role: issue.structural_kind || 'narration' });
    }
  }, `${confirmable.length} review decision${confirmable.length === 1 ? '' : 's'} saved.`);

  return (
    <section ref={sectionRef} className="audiobook-card audiobook-review-queue" aria-label="Human review queue">
      <div className="audiobook-section-title"><div><p className="eyebrow">Human review</p><h2>Review queue</h2>
        <p className="audiobook-subtitle">{issues.length
          ? `${issues.length} open issue${issues.length === 1 ? '' : 's'} in ${chaptersWithIssues} chapter${chaptersWithIssues === 1 ? '' : 's'}. Choose the right speaker for each passage, then confirm it. Rendering waits until the queue is empty.`
          : 'No open issues. Every passage has a confirmed speaker.'}</p></div></div>
      {issues.length > 0 && <div className="audiobook-review-filters">
        <label>Chapter<select aria-label="Filter review issues by chapter" value={chapterFilter} onChange={(event) => setChapterFilter(event.target.value)}>
          <option value="all">All chapters</option>
          {project.chapters.map((chapter) => {
            const count = issues.filter((issue) => issue.chapter_id === chapter.id).length;
            return count ? <option key={chapter.id} value={chapter.id}>{chapter.title} ({count})</option> : null;
          })}
        </select></label>
        <label>Reason<select aria-label="Filter review issues by reason" value={reasonFilter} onChange={(event) => setReasonFilter(event.target.value)}>
          <option value="all">All reasons</option>
          {reasons.map((reason) => <option key={reason} value={reason}>{reviewReasonLabel(reason)} ({issues.filter((issue) => issue.reason === reason).length})</option>)}
        </select></label>
        <label className="audiobook-search-field">Search<input aria-label="Search review issues" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search passages or speakers…" /></label>
        <span className="audiobook-review-count">{shownCount === issues.length ? `${issues.length} issues` : `${shownCount} of ${issues.length} issues`}</span>
        {confirmable.length > 1 && <button type="button" disabled={busy} title={unconfirmable ? `${unconfirmable} shown issue${unconfirmable === 1 ? '' : 's'} without a confirmed speaker will be left open.` : 'Confirm the chosen speaker for every shown issue.'} onClick={confirmAll}>
          {shownCount === issues.length ? `Confirm all ${confirmable.length}` : `Confirm ${confirmable.length} shown`}
        </button>}
      </div>}
      {confirmable.length > 1 && unconfirmable > 0 && <p className="audiobook-detail-muted">{unconfirmable} shown issue{unconfirmable === 1 ? ' has' : 's have'} no speaker from the cast yet and will stay open; choose one or confirm the detected speaker first.</p>}
      {groups.map(({ chapter, issues: chapterIssues }) => <section className="audiobook-review-group" key={chapter.id} aria-label={`Review issues in ${chapter.title}`}>
        <h3>{chapter.title}<span>{chapterIssues.length}</span></h3>
        {chapterIssues.map((issue) => {
          const chosen = chosenSpeaker(issue);
          const candidateInCast = issue.speaker_candidate ? activeSpeakers.some((speaker) => sameName(speaker.canonical_name, issue.speaker_candidate ?? '')) : true;
          return <article className="audiobook-review-item" key={issue.id}>
            <div className="audiobook-review-item-head">
              <span className="audiobook-review-reason">{reviewReasonLabel(issue.reason)}</span>
              {issue.speaker_candidate && <span className="audiobook-detail-muted">Classifier suggests <strong>{issue.speaker_candidate}</strong></span>}
            </div>
            <blockquote>{issueText(issue)}</blockquote>
            {issue.reason === 'POSSIBLE_MISSED_DIALOGUE' && <p className="audiobook-detail-muted">This passage has a speech cue but was extracted as narration. Confirm it as narration only if that is right; speech inside a narration span needs its source segmentation corrected before it can be voiced as dialogue.</p>}
            <div className="audiobook-review-item-actions">
              <select aria-label={`Speaker for review ${issue.id}`} value={chosen} onChange={(event) => setReviewSpeakers((previous) => ({ ...previous, [issue.id]: event.target.value }))}>
                <option value="">Choose speaker</option>
                {project.speakers.map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.canonical_name}{speaker.status === 'proposed' ? ' · detected' : ''}</option>)}
              </select>
              <button type="button" disabled={busy || !chosen} onClick={() => void action(() => audiobookApi.resolveReview(project.id, issue.id, { speaker_id: chosen, role: issue.structural_kind || 'narration' }), 'Review decision saved.')}>
                {issue.reason === 'POSSIBLE_MISSED_DIALOGUE' ? 'Confirm narration' : 'Confirm speaker'}
              </button>
              {!candidateInCast && <button type="button" disabled={busy} onClick={() => void action(() => audiobookApi.createSpeaker(project.id, { canonical_name: issue.speaker_candidate ?? '' }), `${issue.speaker_candidate} added to the cast.`)}>Add “{issue.speaker_candidate}” to the cast</button>}
              <button type="button" onClick={() => { setChapterId(issue.chapter_id); setSelectedSpanId(issue.span_id); navigateLibrary('projects'); }}>Show in manuscript</button>
            </div>
          </article>;
        })}
      </section>)}
      {issues.length > 0 && shownCount === 0 && <p className="audiobook-empty-state">No issues match these filters.</p>}
    </section>
  );
}
