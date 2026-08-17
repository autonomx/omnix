import type { ReviewRpgPairStatus } from './reviewRpgPairStatus';
import { formatReviewRpgPairLabel } from './reviewRpgPairLabel';

export interface ReviewRpgPairBadge {
  text: string;
  ariaLabel: string;
  readOnly: true;
  passive: true;
}

export function createReviewRpgPairBadge(status: ReviewRpgPairStatus): ReviewRpgPairBadge {
  const text = formatReviewRpgPairLabel(status);
  return {
    text,
    ariaLabel: `Status: ${text}`,
    readOnly: true,
    passive: true,
  };
}
