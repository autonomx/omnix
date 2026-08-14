import type { OmnixModeId } from './omnixModeIds';

export interface ReviewChecklistItem {
  id: string;
  label: string;
  checked: boolean;
}

export function createReviewChecklistState(mode: OmnixModeId, userReviewed = false): ReviewChecklistItem[] {
  return [
    { id: 'user-reviewed', label: 'User reviewed proposal', checked: userReviewed },
    { id: 'no-execution', label: 'No execution performed', checked: true },
    {
      id: 'simulation-validation',
      label: 'Simulation validation required for RPG',
      checked: mode === 'rpg',
    },
    { id: 'risks-visible', label: 'Risks visible before use', checked: true },
  ];
}
