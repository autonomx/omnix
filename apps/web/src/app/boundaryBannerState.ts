import type { OmnixModeId } from './omnixModeIds';

export interface BoundaryBannerState {
  visible: boolean;
  title: string;
  message: string;
  proposalOnly: boolean;
  simulationValidates: boolean;
}

export function createBoundaryBannerState(mode: OmnixModeId): BoundaryBannerState {
  if (mode === 'rpg') {
    return {
      visible: true,
      title: 'Proposal only',
      message: 'RPG simulation validates truth before any state changes.',
      proposalOnly: true,
      simulationValidates: true,
    };
  }
  return {
    visible: false,
    title: '',
    message: '',
    proposalOnly: true,
    simulationValidates: false,
  };
}
