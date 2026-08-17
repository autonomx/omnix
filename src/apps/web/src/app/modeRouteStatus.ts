import type { OmnixModePath } from './omnixModeRouter';

export interface ModeRouteStatusInfo {
  path: OmnixModePath;
  label: string;
  tone: 'ready' | 'review' | 'runtime';
}

const MODE_ROUTE_STATUS: Record<OmnixModePath, ModeRouteStatusInfo> = {
  direct: { path: 'direct', label: 'Direct provider', tone: 'ready' },
  live: { path: 'live', label: 'Live session', tone: 'ready' },
  adapter: { path: 'adapter', label: 'Adapter review', tone: 'review' },
  review: { path: 'review', label: 'Review required', tone: 'review' },
  audio: { path: 'audio', label: 'Audio pipeline', tone: 'runtime' },
  sim: { path: 'sim', label: 'Simulation', tone: 'runtime' },
};

export function getModeRouteStatusInfo(path: OmnixModePath): ModeRouteStatusInfo {
  return MODE_ROUTE_STATUS[path];
}
