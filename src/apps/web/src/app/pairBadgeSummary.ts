export interface PairBadgeSummary {
  text: string;
  visibleCount: number;
  readOnly: true;
}

export function createPairBadgeSummary(input: {
  text: string;
  reviewVisible?: boolean;
  rpgVisible?: boolean;
}): PairBadgeSummary {
  return {
    text: input.text,
    visibleCount: [input.reviewVisible, input.rpgVisible].filter(Boolean).length,
    readOnly: true,
  };
}
