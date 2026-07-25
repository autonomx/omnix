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

export interface RpgWorldGenerationReviewReport {
  schema_version?: string;
  status: string;
  blocking: boolean;
  error_type?: string;
  reason_codes: string[];
  issues: RpgWorldGenerationReviewIssue[];
  summary?: string;
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
  provider: Record<string, unknown>;
  dependency_hashes: Record<string, string>;
  dependency_trust: Record<string, string>;
  job_id: string;
  created_at: string;
  updated_at: string;
  previous_result?: RpgWorldGenerationTopicResult | null;
}

interface ReviewListResponse {
  ok: boolean;
  run_id: string;
  parent_run_id?: string | null;
  topic_results: RpgWorldGenerationTopicResult[];
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
};
