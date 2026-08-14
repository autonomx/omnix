export function sidecarStatusPath(): `/api/${string}` {
  return '/api/sidecar/status';
}

export function sidecarStatusQueryKey(): readonly ['sidecar-status'] {
  return ['sidecar-status'] as const;
}

export function sidecarStatusRefreshKey(scope = 'default'): readonly ['sidecar-status', 'refresh', string] {
  return ['sidecar-status', 'refresh', scope.trim() || 'default'] as const;
}
