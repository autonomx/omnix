export interface CfgState {
  active: boolean;
  ready: boolean;
  readOnly: true;
  passive: true;
}

export function cfgState(active = false, ready = false): CfgState {
  return {
    active,
    ready: active && ready,
    readOnly: true,
    passive: true,
  };
}
