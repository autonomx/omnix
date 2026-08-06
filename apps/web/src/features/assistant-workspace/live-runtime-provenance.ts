export const LIVE_COORDINATION_SCHEMA = 2;

export type LiveRuntimeProvenance = {
  git_sha: string;
  git_dirty: boolean | null;
  build_id: string;
  coordination_schema: number;
  direct_final_routing: true;
};

function envValue(name: string): string | undefined {
  const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};
  const value = env[name]?.trim();
  return value || undefined;
}

function envBoolean(name: string): boolean | null {
  const value = envValue(name)?.toLowerCase();
  if (value === undefined) return null;
  if (['1', 'true', 'yes', 'dirty'].includes(value)) return true;
  if (['0', 'false', 'no', 'clean'].includes(value)) return false;
  return null;
}

export function currentLiveRuntimeProvenance(): LiveRuntimeProvenance {
  const gitSha = envValue('VITE_GIT_SHA') ?? 'unknown';
  return {
    git_sha: gitSha,
    git_dirty: envBoolean('VITE_GIT_DIRTY'),
    build_id: envValue('VITE_BUILD_ID') ?? `dev-${gitSha.slice(0, 12)}`,
    coordination_schema: LIVE_COORDINATION_SCHEMA,
    direct_final_routing: true,
  };
}

export function emitLiveRuntimeProvenance(): LiveRuntimeProvenance {
  const provenance = currentLiveRuntimeProvenance();
  window.dispatchEvent(new CustomEvent('omnix:live-runtime-bootstrap', { detail: provenance }));
  console.info('[Omnix Voice Perf]', { event: 'live_runtime_bootstrap', ...provenance });
  return provenance;
}
