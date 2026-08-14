import type { ReviewRpgPairStatus } from './reviewRpgPairStatus';

export function formatReviewRpgPairLabel(status: ReviewRpgPairStatus): string {
  if (status.reviewVisible && status.rpgVisible) {
    return `${status.label} · read-only`;
  }
  if (status.reviewVisible) {
    return 'Review ready · read-only';
  }
  if (status.rpgVisible) {
    return 'RPG proposal ready · read-only';
  }
  return `${status.label} · read-only`;
}
