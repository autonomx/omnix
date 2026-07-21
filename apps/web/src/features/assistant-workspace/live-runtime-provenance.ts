export const LIVE_COORDINATION_SCHEMA = 2;

export type LiveRuntimeProvenance = {
  git_sha: string;
  build_id: string;
  coordination_schema: number;
  direct_final_routing: true;
};

function envValue(name: string): string | undefined {
  const env = import.meta.env as Record<string, string | undefined>;
  const value = env[name]?.trim();
  return value || undefined;
}

export function currentLiveRuntimeProvenance(): LiveRuntimeProvenance {
  const gitSha = envValue('VITE_GIT_SHA') ?? 'unknown';
  return {
    git_sha: gitSha,
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
