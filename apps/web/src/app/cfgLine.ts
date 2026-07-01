import type { CfgState } from './cfgState';

export function cfgLine(state: CfgState): string {
  return state.ready ? 'Ready' : 'Waiting';
}
