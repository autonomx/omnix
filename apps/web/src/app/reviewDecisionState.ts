import type { ReviewDecision, ReviewDecisionDraft } from './reviewDecisionDraft';

export interface ReviewDecisionState {
  label: string;
  status: ReviewDecision;
  notes: string;
  executes: false;
}

const LABELS: Record<ReviewDecision, string> = {
  pending: 'Pending review',
  approved: 'Approved label only',
  rejected: 'Rejected label only',
};

export function createReviewDecisionState(draft: ReviewDecisionDraft): ReviewDecisionState {
  return {
    label: LABELS[draft.decision],
    status: draft.decision,
    notes: draft.notes,
    executes: false,
  };
}
