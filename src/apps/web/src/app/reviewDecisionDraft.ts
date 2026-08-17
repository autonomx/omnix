export type ReviewDecision = 'pending' | 'approved' | 'rejected';

export interface ReviewDecisionDraft {
  item_id: string;
  decision: ReviewDecision;
  notes: string;
  executes: false;
}

export interface ReviewDecisionValidation {
  ok: boolean;
  errors: string[];
  executes: false;
}

const REVIEW_DECISIONS = new Set(['pending', 'approved', 'rejected']);

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

export function validateReviewDecisionDraft(value: Partial<ReviewDecisionDraft>): ReviewDecisionValidation {
  const errors: string[] = [];
  if (!value.item_id?.trim()) {
    errors.push('item_id_required');
  }
  if (!REVIEW_DECISIONS.has(String(value.decision))) {
    errors.push('unknown_decision');
  }
  return { ok: errors.length === 0, errors, executes: false };
}
