export type MemoryScope = 'global' | 'workspace' | 'project' | 'session';
export type MemoryCategory = 'preference' | 'fact' | 'project' | 'relationship' | 'instruction';
export type CompanionRolloutStage =
  | 'authority_only'
  | 'shadow'
  | 'read_only_pilot'
  | 'explicit_typed'
  | 'review_required'
  | 'automatic_assertions'
  | 'gentle_initiative'
  | 'active_initiative'
  | 'paralinguistic_pilot';

export interface ManagedMemoryRecord {
  id: string;
  scope: MemoryScope;
  scope_id: string;
  category: MemoryCategory;
  kind: string;
  structured_payload: Record<string, unknown>;
  source: string;
  content: string;
  confidence: number;
  pinned: boolean;
  trust_level: string;
  provenance_type: string;
  provenance_id?: string | null;
  status: string;
  revision: number;
  created_at: string;
  updated_at: string;
  expires_at?: string | null;
}

export interface ManagedMemoryCandidate {
  id: string;
  source_session_id: string;
  source_message_id: string;
  proposed_scope: MemoryScope;
  proposed_scope_id: string;
  proposed_category: MemoryCategory;
  proposed_content: string;
  confidence: number;
  source: string;
  trust_level: string;
  status: string;
  created_at: string;
}

export type MemoryCandidateReviewResult = ManagedMemoryRecord | ManagedMemoryCandidate;

export interface ManagedMemoryList {
  records: ManagedMemoryRecord[];
  total: number;
  session_id: string;
}

export interface ManagedMemoryCandidateList {
  candidates: ManagedMemoryCandidate[];
  total: number;
  session_id: string;
}

export interface SessionMemorySnapshotItem {
  memory_record_id: string;
  record_revision: number;
  content: string;
  active: boolean;
  invalidation_reason?: string | null;
}

export interface AssistantMemoryRuntimeSettings {
  curated_memory_enabled: boolean;
  suggestions_enabled: boolean;
  history_recall_enabled: boolean;
  compaction_enabled: boolean;
  hermes_sync_enabled: boolean;
  require_approval_for_inferred_memory: boolean;
  automatic_direct_assertion_memory: boolean;
  proactive_memory_enabled: boolean;
  paralinguistic_signals_enabled: boolean;
  transcript_retention_enabled: boolean;
  companion_master_enabled: boolean;
  companion_rollout_stage: CompanionRolloutStage;
  memory_token_budget: number;
  history_token_budget: number;
  retention_days: number;
  show_memory_use_indicator: boolean;
}

export interface AssistantMemoryRuntimeStatus {
  settings: AssistantMemoryRuntimeSettings;
  settings_path: string;
  environment_overrides: string[];
  approval_policy_locked: boolean;
  diagnostics_policy: 'content_free';
}

export interface CompanionMemoryMetrics {
  turns: number;
  counters: Record<string, number>;
  totals: Record<string, number>;
  maxima: Record<string, number>;
  diagnostics_policy: 'content_free';
}

export interface MemoryUsageItem {
  memory_id: string;
  selection_reason: string;
  activation_score: number;
  section: string;
  source_revision: number;
}

export interface MemoryUsageResponse {
  session_id: string;
  recorded_at: string;
  items: MemoryUsageItem[];
  diagnostics_policy: 'content_free';
}

export interface MemoryExportResponse {
  exported_at: string;
  owner_type: string;
  owner_id: string;
  records: ManagedMemoryRecord[];
  candidates: ManagedMemoryCandidate[];
}

export interface MemoryResetResponse {
  ok: true;
  owner_type: string;
  owner_id: string;
  record_count: number;
  candidate_count: number;
  snapshot_count: number;
}

export interface SessionMemoryState {
  session_id: string;
  memory_enabled: boolean;
  snapshot_id?: string | null;
  snapshot_revision?: number | null;
  memory_record_count: number;
  last_refreshed_at?: string | null;
  snapshot?: {
    snapshot_id: string;
    revision: number;
    token_estimate: number;
    active_count: number;
    invalidated_count: number;
    items: SessionMemorySnapshotItem[];
  } | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Memory request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function revisionBody(sessionId: string, record: ManagedMemoryRecord): RequestInit {
  return jsonInit('POST', { session_id: sessionId, expected_revision: record.revision });
}

export const memoryClient = {
  list(sessionId: string, query = '', scope = '', category = ''): Promise<ManagedMemoryList> {
    const params = new URLSearchParams({ session_id: sessionId });
    if (query) params.set('query', query);
    if (scope) params.set('scope', scope);
    if (category) params.set('category', category);
    return request(`/api/assistant/memory?${params.toString()}`);
  },
  archived(sessionId: string): Promise<ManagedMemoryList> {
    return request(`/api/assistant/memory/archived?session_id=${encodeURIComponent(sessionId)}`);
  },
  recentAutomatic(sessionId: string): Promise<{ session_id: string; records: ManagedMemoryRecord[] }> {
    return request(`/api/assistant/memory/recent-automatic?session_id=${encodeURIComponent(sessionId)}`);
  },
  usage(sessionId: string): Promise<MemoryUsageResponse> {
    return request(`/api/assistant/memory/usage?session_id=${encodeURIComponent(sessionId)}`);
  },
  exportMemory(sessionId: string): Promise<MemoryExportResponse> {
    return request(`/api/assistant/memory/export?session_id=${encodeURIComponent(sessionId)}`);
  },
  reset(sessionId: string): Promise<MemoryResetResponse> {
    return request(`/api/assistant/memory/reset?session_id=${encodeURIComponent(sessionId)}`, { method: 'POST' });
  },
  create(sessionId: string, input: { scope: MemoryScope; category: MemoryCategory; content: string; pinned: boolean }): Promise<ManagedMemoryRecord> {
    return request('/api/assistant/memory', jsonInit('POST', { session_id: sessionId, ...input }));
  },
  edit(sessionId: string, record: ManagedMemoryRecord, content: string): Promise<ManagedMemoryRecord> {
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}`, jsonInit('PATCH', {
      session_id: sessionId,
      expected_revision: record.revision,
      content,
    }));
  },
  pin(sessionId: string, record: ManagedMemoryRecord, pinned: boolean): Promise<ManagedMemoryRecord> {
    const action = pinned ? 'pin' : 'unpin';
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}/${action}`, revisionBody(sessionId, record));
  },
  move(sessionId: string, record: ManagedMemoryRecord, targetScope: MemoryScope): Promise<ManagedMemoryRecord> {
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}/move`, jsonInit('POST', {
      session_id: sessionId,
      expected_revision: record.revision,
      target_scope: targetScope,
    }));
  },
  archive(sessionId: string, record: ManagedMemoryRecord): Promise<ManagedMemoryRecord> {
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}/archive`, revisionBody(sessionId, record));
  },
  restore(sessionId: string, record: ManagedMemoryRecord): Promise<ManagedMemoryRecord> {
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}/restore`, revisionBody(sessionId, record));
  },
  undo(sessionId: string, record: ManagedMemoryRecord): Promise<{ ok: true; memory_id: string }> {
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}/undo`, revisionBody(sessionId, record));
  },
  forget(sessionId: string, record: ManagedMemoryRecord): Promise<{ ok: true; memory_id: string }> {
    const params = new URLSearchParams({ session_id: sessionId, expected_revision: String(record.revision) });
    return request(`/api/assistant/memory/${encodeURIComponent(record.id)}?${params.toString()}`, { method: 'DELETE' });
  },
  candidates(sessionId: string): Promise<ManagedMemoryCandidateList> {
    return request(`/api/assistant/memory/candidates/pending?session_id=${encodeURIComponent(sessionId)}`);
  },
  approve(sessionId: string, candidateId: string): Promise<MemoryCandidateReviewResult> {
    return request(`/api/assistant/memory/candidates/${encodeURIComponent(candidateId)}/approve`, jsonInit('POST', {
      session_id: sessionId,
      pinned: false,
    }));
  },
  reject(sessionId: string, candidateId: string): Promise<MemoryCandidateReviewResult> {
    return request(`/api/assistant/memory/candidates/${encodeURIComponent(candidateId)}/reject`, jsonInit('POST', {
      session_id: sessionId,
      pinned: false,
    }));
  },
  sessionState(sessionId: string): Promise<SessionMemoryState> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/memory`);
  },
  refresh(sessionId: string, expectedRevision?: number | null): Promise<SessionMemoryState> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/memory/refresh`, jsonInit('POST', {
      expected_snapshot_revision: expectedRevision ?? null,
      token_budget: 4000,
    }));
  },
  settings(): Promise<AssistantMemoryRuntimeStatus> {
    return request('/api/assistant/memory/settings');
  },
  updateSettings(update: Partial<AssistantMemoryRuntimeSettings>): Promise<AssistantMemoryRuntimeStatus> {
    return request('/api/assistant/memory/settings', jsonInit('POST', update));
  },
  metrics(): Promise<CompanionMemoryMetrics> {
    return request('/api/assistant/memory/metrics');
  },
};
