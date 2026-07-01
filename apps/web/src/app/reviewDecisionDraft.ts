export type ReviewDecision = 'pending' | 'approved' | 'rejected';

export interface ReviewDecisionDraft {
  item_id: string;
  decision: ReviewDecision;
  notes: string;
  executes: false;
}

export function createReviewDecisionDraft(
  itemId: string,
  decision: ReviewDecision = 'pending',
  notes = '',
): ReviewDecisionDraft {
  return {
    item_id: itemId.trim(),
    decision,
    notes: notes.trim(),
    executes: false,
  };
}
