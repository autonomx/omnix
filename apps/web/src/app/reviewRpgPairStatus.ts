export interface ReviewRpgPairStatus {
  reviewVisible: boolean;
  rpgVisible: boolean;
  label: string;
  readOnly: true;
  passive: true;
}

export function createReviewRpgPairStatus(input: {
  reviewReady?: boolean;
  rpgReady?: boolean;
} = {}): ReviewRpgPairStatus {
  const reviewVisible = input.reviewReady === true;
  const rpgVisible = input.rpgReady === true;
  return {
    reviewVisible,
    rpgVisible,
    label: reviewVisible && rpgVisible ? 'Review and RPG proposal ready' : 'Awaiting review context',
    readOnly: true,
    passive: true,
  };
}
