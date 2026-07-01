export function sidecarStatusPath(): `/api/${string}` {
  return '/api/sidecar/status';
}

export function sidecarStatusQueryKey(): readonly ['sidecar-status'] {
  return ['sidecar-status'] as const;
}
