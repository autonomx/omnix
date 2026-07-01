export interface AuditDisplayState {
  source: string;
  status: 'ready' | 'unavailable';
  timestamp: string;
  reviewRequired: boolean;
  readOnly: boolean;
  executes: boolean;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function createAuditDisplayState(payload?: unknown): AuditDisplayState {
  const record = asRecord(payload);
  const source = typeof record.source === 'string' ? record.source : 'unknown';
  const timestamp = typeof record.timestamp === 'string' ? record.timestamp : '';
  return {
    source,
    status: source === 'unknown' ? 'unavailable' : 'ready',
    timestamp,
    reviewRequired: record.review_required !== false,
    readOnly: record.read_only !== false,
    executes: false,
  };
}
