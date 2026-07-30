export interface RpgWorldGenerationReviewIssue {
  code: string;
  topic_id: string;
  entity_id?: string;
  field_id?: string;
  message?: string;
  expected?: string;
  allowed_domains?: string[];
  candidates?: string[];
  supplied_value?: unknown;
}

export interface RpgWorldGenerationReviewWaiver {
  status: 'active' | 'none' | string;
  reason?: string;
  accepted_by?: string;
  accepted_at?: string;
}

export interface RpgWorldGenerationValidationAttempt {
  schema_version: string;
  attempt_id: string;
  attempt_number: number;
  trigger: 'generation' | 'manual_retry' | string;
  run_id: string;
  topic_id: string;
  job_id: string;
  candidate_hash: string;
  result_status: string;
  validation_status: string;
  reason_codes: string[];
  issues: RpgWorldGenerationReviewIssue[];
  validation_hash: string;
  provider: Record<string, unknown>;
}

export interface RpgWorldGenerationFindingFingerprint {
  code: string;
  topic_id: string;
  entity_id: string;
  field_id: string;
  bad_value: string;
}

export interface RpgWorldGenerationRepairEvaluation {
  schema_version: string;
  outcome:
    | 'repaired'
    | 'partially_repaired'
    | 'no_op'
    | 'regressed'
    | 'replaced_with_new_failure'
    | 'not_applicable'
    | string;
  candidate_changed: boolean;
  original_finding_count: number;
  remaining_finding_count: number;
  repaired_finding_count: number;
  introduced_finding_count: number;
  remaining_finding_fingerprints: RpgWorldGenerationFindingFingerprint[];
  repaired_finding_fingerprints: RpgWorldGenerationFindingFingerprint[];
  introduced_finding_fingerprints: RpgWorldGenerationFindingFingerprint[];
  changed_bad_values: Array<{
    location: string[];
    previous_bad_value: string;
    current_bad_value: string;
  }>;
}

export interface RpgWorldGenerationReviewReport {
  schema_version?: string;
  status: string;
  blocking: boolean;
  validation_blocking?: boolean;
  review_decision?: string;
  validation_status?: 'passed' | 'failed' | 'not_run' | string;
  waiver_status?: 'active' | 'none' | string;
  waiver?: RpgWorldGenerationReviewWaiver;
  error_type?: string;
  reason_codes: string[];
  issues: RpgWorldGenerationReviewIssue[];
  outstanding_reason_codes?: string[];
  outstanding_findings?: RpgWorldGenerationReviewIssue[];
  attempt_history_schema?: string;
  attempt_history?: RpgWorldGenerationValidationAttempt[];
  summary?: string;
  accepted_at?: string;
  accepted_by?: string;
  previous_validation?: RpgWorldGenerationReviewReport;
}

export interface RpgWorldGenerationReviewState {
  review_decision: 'accepted' | 'pending' | string;
  validation_status: 'passed' | 'failed' | 'not_run' | string;
  waiver_status: 'active' | 'none' | string;
  outstanding_finding_count: number;
  outstanding_findings: RpgWorldGenerationReviewIssue[];
  outstanding_reason_codes: string[];
  attempt_count: number;
  attempt_history: RpgWorldGenerationValidationAttempt[];
  repair_evaluation: RpgWorldGenerationRepairEvaluation | null;
  consecutive_no_op_count: number;
  retry_budget_exhausted: boolean;
}

export interface RpgWorldGenerationReviewDecision {
  decision: 'accept' | 'keep' | 'replace';
  candidate_hash: string;
  promoted_hash?: string;
  decided_at?: string;
  edited?: boolean;
  review_decision?: string;
  validation_status?: string;
  waiver_status?: string;
  outstanding_finding_count?: number;
}

export interface RpgWorldGenerationFailureArtifact {
  schema_version: 'rpg_world_forge_failure_artifact_v1' | string;
  artifact_id: string;
  run_id: string;
  job_id: string;
  topic_id: string;
  attempt: number;
  stage: string;
  provider: string;
  model: string;
  structured_mode: string;
  strategy_identity: string;
  provider_schema_hash: string;
  canonical_contract_hash: string;
  raw_response_hash: string;
  raw_response_bytes: number;
  sanitized_excerpt: string;
  issues: Array<{ stage: string; path: string; code: string; message: string }>;
  deterministic_repairs: string[];
  correction_attempted: boolean;
  correction_result: string;
  created_at: string;
}

export interface RpgWorldGenerationTopicResult {
  run_id: string;
  world_id: string;
  draft_revision: number;
  topic_id: string;
  status: 'accepted' | 'needs_review' | 'failed' | 'blocked';
  candidate: Record<string, unknown> | null;
  candidate_hash: string;
  validation: RpgWorldGenerationReviewReport;
  review_state?: RpgWorldGenerationReviewState;
  provider: Record<string, unknown>;
  failure_artifact?: RpgWorldGenerationFailureArtifact | null;
  dependency_hashes: Record<string, string>;
  dependency_trust: Record<string, string>;
  job_id: string;
  created_at: string;
  updated_at: string;
  previous_result?: RpgWorldGenerationTopicResult | null;
  decision?: RpgWorldGenerationReviewDecision | null;
}

export interface RpgWorldGenerationReviewAnalytics {
  status: Record<string, number>;
  by_code: Record<string, number>;
  by_field: Record<string, number>;
  by_topic: Record<string, number>;
  by_domain: Record<string, number>;
  by_model: Record<string, number>;
  by_prompt_version: Record<string, number>;
  by_provider: Record<string, number>;
}

interface ReviewListResponse {
  ok: boolean;
  run_id: string;
  parent_run_id?: string | null;
  topic_results: RpgWorldGenerationTopicResult[];
  analytics: RpgWorldGenerationReviewAnalytics;
  review_decisions: Record<string, RpgWorldGenerationReviewDecision>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = await response.text();
  if (!response.ok) {
    let message = body;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown; error?: unknown };
      message = JSON.stringify(parsed.detail ?? parsed.error ?? parsed);
    } catch {
      // Preserve the raw body.
    }
    throw new Error(`World generation review request failed (${response.status}): ${message}`);
  }
  return (body ? JSON.parse(body) : {}) as T;
}

export const rpgWorldGenerationReviewClient = {
  list(runId: string): Promise<ReviewListResponse> {
    return request(`/api/rpg/world-generation/${encodeURIComponent(runId)}/results`);
  },

  topic(runId: string, topicId: string): Promise<{
    ok: boolean;
    parent_run_id?: string | null;
    topic_result: RpgWorldGenerationTopicResult;
  }> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/results/${encodeURIComponent(topicId)}`,
    );
  },

  retry(
    runId: string,
    body: {
      topic_ids?: string[];
      retry_scopes?: Record<string, Record<string, unknown>>;
    } = {},
  ): Promise<Record<string, unknown>> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/retry-review`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
  },

  accept(
    runId: string,
    topicId: string,
    body: {
      candidate?: Record<string, unknown>;
      expected_candidate_hash?: string;
      waiver_reason?: string;
    } = {},
  ): Promise<Record<string, unknown>> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/results/${encodeURIComponent(topicId)}/accept`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
  },

  acceptAll(
    runId: string,
    body: {
      topic_ids?: string[];
      waiver_reason?: string;
      waiver_reasons?: Record<string, string>;
    } = {},
  ): Promise<Record<string, unknown>> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/accept-all`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
  },

  decide(
    runId: string,
    topicId: string,
    decision: 'keep' | 'replace',
  ): Promise<Record<string, unknown>> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/results/${encodeURIComponent(topicId)}/decision`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      },
    );
  },
};
