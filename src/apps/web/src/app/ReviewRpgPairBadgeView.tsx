import { createReviewRpgPairBadge } from './reviewRpgPairBadge';
import type { ReviewRpgPairStatus } from './reviewRpgPairStatus';

export function ReviewRpgPairBadgeView({ status }: { status: ReviewRpgPairStatus }) {
  const badge = createReviewRpgPairBadge(status);

  return (
    <span aria-label={badge.ariaLabel} data-read-only={badge.readOnly} data-passive={badge.passive}>
      {badge.text}
    </span>
  );
}
