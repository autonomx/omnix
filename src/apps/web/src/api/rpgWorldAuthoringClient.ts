import type { RpgWorldGenerationRun, RpgWorldSummary } from './rpgWorldLibraryClient';

export type RpgAuthoringGroup = 'workspace' | 'world' | 'lore' | 'game-master';
export type RpgAuthoringPageKind = 'document' | 'collection';

export interface RpgAuthoringSection {
  id: string;
  label: string;
  group: RpgAuthoringGroup;
  page_kind: RpgAuthoringPageKind;
  topic_ids: string[];
  entity_kind?: string;
  dependencies: string[];
  required_before_launch: boolean;
  supports_generation: boolean;
  supports_images: boolean;
  supports_entity_editing: boolean;
  operational_status: string;
  editorial_status: string;
  entity_count: number;
}

export interface RpgWorldTokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  provider_reported_topics: number;
  estimated_topics: number;
  unavailable_topics: number;
  topic_count: number;
  in_flight_topics?: number;
  generation_duration_ms?: number;
  timed_topics?: number;
  repair_count?: number;
  repair_tokens?: number;
  provider_reported_repairs?: number;
  estimated_repairs?: number;
}

export interface RpgAuthoringManifestResponse {
  ok: boolean;
  world: RpgWorldSummary;
  sections: RpgAuthoringSection[];
  generation: RpgWorldGenerationRun | Record<string, never>;
  token_usage?: RpgWorldTokenUsage;
}

export interface RpgAuthoringCardHighlight {
  label: string;
  value: unknown;
}

export interface RpgAuthoringCardGroup {
  label: string;
  items: unknown[];
  style: 'chips' | 'list' | string;
}

export interface RpgAuthoringCardPresentation {
  variant: string;
  eyebrow: string;
  badges: unknown[];
  highlights: RpgAuthoringCardHighlight[];
  groups: RpgAuthoringCardGroup[];
}

export interface RpgAuthoringDossierQuote {
  text: string;
  attribution?: string;
}

export interface RpgAuthoringDossierQuickFact {
  label: string;
  value: unknown;
}

export interface RpgAuthoringDossierSection {
  id: string;
  title: string;
  paragraphs: string[];
}

export interface RpgAuthoringEntityDossier {
  schema_version: 'rpg_world_entity_dossier_v1' | string;
  subtitle?: string;
  quote?: RpgAuthoringDossierQuote | null;
  quick_facts: RpgAuthoringDossierQuickFact[];
  sections: RpgAuthoringDossierSection[];
  related_entity_ids: string[];
  generated_from_legacy?: boolean;
  quality_enriched?: boolean;
}

export interface RpgAuthoringEntityCard {
  id: string;
  title: string;
  summary: string;
  short_summary?: string;
  dossier?: RpgAuthoringEntityDossier;
  kind: string;
  card_type: string;
  image_target_id?: string;
  presentation: RpgAuthoringCardPresentation;
  metadata: Record<string, unknown>;
}

export interface RpgAuthoringDocumentBlock {
  kind: 'section' | 'facts' | 'json' | string;
  title?: string;
  body?: string;
  items?: Array<Record<string, unknown>>;
  value?: unknown;
}

export interface RpgAuthoringTopic {
  topic_id: string;
  draft_revision: number;
  source: string;
  status: string;
  content: Record<string, unknown>;
  directives: Record<string, unknown>;
  dependency_hashes: Record<string, string>;
  input_hash: string;
  content_hash: string;
  provenance: Record<string, unknown>;
  updated_at: string;
}

export interface RpgAuthoringTopicHistory extends RpgAuthoringTopic {
  history_sequence: number;
  captured_at: string;
  topic_updated_at: string;
}

export interface RpgAuthoringEntityHistory {
  history_sequence: number;
  operation: 'manual_edit' | 'regenerate' | 'manual_dossier_edit' | 'regenerate_dossier' | 'restore' | string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  topic_content_hash: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface RpgAuthoringDocumentPage {
  ok: boolean;
  section_id: string;
  page_kind: 'document';
  title: string;
  summary?: string;
  body: RpgAuthoringDocumentBlock[];
  related_entities: Array<Record<string, unknown>>;
  topic?: RpgAuthoringTopic;
}

export interface RpgAuthoringCollectionPage {
  ok: boolean;
  section_id: string;
  page_kind: 'collection';
  title: string;
  entities: RpgAuthoringEntityCard[];
  filters: Array<Record<string, unknown>>;
  sort_options: string[];
  topic?: RpgAuthoringTopic;
}

export interface RpgAuthoringEntityMutationResponse {
  ok: boolean;
  topic: RpgAuthoringTopic;
  entity: Record<string, unknown>;
  stale_topic_ids: string[];
  stale_entity_ids: string[];
  canonical_fields_preserved?: boolean;
  editorial_only?: boolean;
}

export interface RpgAuthoringDossierPreviewResponse {
  ok: boolean;
  preview_only: boolean;
  world_id: string;
  topic_id: string;
  entity_id: string;
  expected_draft_revision: number;
  expected_content_hash: string;
  short_summary: string;
  dossier: RpgAuthoringEntityDossier;
  generation: Record<string, unknown>;
  canonical_fields_preserved: boolean;
  stored: false;
}

export interface RpgDossierQualityMetrics {
  entities: number;
  rich_dossiers: number;
  projected_legacy_dossiers: number;
  invalid_or_thin_dossiers: number;
  heading_repairs: number;
  coverage_percent: number;
  average_words: number;
  unresolved_related_entity_ids: number;
}

export interface RpgDossierQualityTopicMetrics {
  topic_id: string;
  entities: number;
  rich: number;
  projected: number;
  invalid: number;
  words: number;
  coverage_percent: number;
  average_words: number;
}

export interface RpgDossierEnrichmentCandidate {
  topic_id: string;
  entity_id: string;
  title: string;
  word_count: number;
  generated_from_legacy: boolean;
  issues: string[];
}

export interface RpgDossierEnrichmentRequest {
  all_candidates?: boolean;
  candidates?: Array<Pick<RpgDossierEnrichmentCandidate, 'topic_id' | 'entity_id'>>;
  directives?: Record<string, unknown>;
  dry_run?: boolean;
  limit?: number;
}

export interface RpgWorldDossierQualityResponse {
  ok: boolean;
  world_id: string;
  draft_revision: number;
  schema_version: string;
  metrics: RpgDossierQualityMetrics;
  by_topic: RpgDossierQualityTopicMetrics[];
  unresolved_related_entity_ids: string[];
  enrichment_candidates: RpgDossierEnrichmentCandidate[];
}

export interface RpgWorldDossierEnrichmentResponse {
  ok: boolean;
  world_id: string;
  dry_run: boolean;
  candidate_count?: number;
  candidates?: RpgDossierEnrichmentCandidate[];
  attempted?: number;
  completed?: Array<{ topic_id: string; entity_id: string; content_hash: string }>;
  failed?: Array<{ topic_id: string; entity_id: string; error: string }>;
  metrics?: RpgDossierQualityMetrics;
  quality?: RpgWorldDossierQualityResponse;
}

export type RpgAuthoringPage = RpgAuthoringDocumentPage | RpgAuthoringCollectionPage;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const text = await response.text();
  if (!response.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown };
      const candidate = parsed.detail ?? parsed.error;
      detail = typeof candidate === 'string' ? candidate : JSON.stringify(candidate);
    } catch {
      // Preserve the raw response.
    }
    throw new Error(`Omnix API request failed with status ${response.status}${detail ? `: ${detail}` : ''}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

function jsonPatch(body: Record<string, unknown>): RequestInit {
  return {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

function jsonPost(body: object): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

function entityPath(worldId: string, topicId: string, entityId: string): string {
  return `/api/rpg/worlds/${encodeURIComponent(worldId)}/topics/${encodeURIComponent(topicId)}/entities/${encodeURIComponent(entityId)}`;
}

export const rpgWorldAuthoringClient = {
  manifest(worldId: string): Promise<RpgAuthoringManifestResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/authoring-manifest`);
  },

  section(worldId: string, sectionId: string): Promise<RpgAuthoringPage> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/authoring-sections/${encodeURIComponent(sectionId)}`,
    );
  },

  dossierQuality(worldId: string): Promise<RpgWorldDossierQualityResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/dossier-quality`);
  },

  enrichDossiers(
    worldId: string,
    body: RpgDossierEnrichmentRequest,
  ): Promise<RpgWorldDossierEnrichmentResponse> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/enrich-dossiers`,
      jsonPost(body),
    );
  },

  updateWorld(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; world: RpgWorldSummary }> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}`, jsonPatch(body));
  },

  topic(worldId: string, topicId: string): Promise<{
    ok: boolean;
    world: RpgWorldSummary;
    topic: RpgAuthoringTopic;
    history: RpgAuthoringTopicHistory[];
  }> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/topics/${encodeURIComponent(topicId)}`);
  },

  updateTopic(
    worldId: string,
    topicId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; topic: RpgAuthoringTopic; stale_topic_ids: string[] }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/topics/${encodeURIComponent(topicId)}`,
      jsonPatch(body),
    );
  },

  restoreTopic(
    worldId: string,
    topicId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; topic: RpgAuthoringTopic; stale_topic_ids: string[] }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/topics/${encodeURIComponent(topicId)}/restore`,
      jsonPost(body),
    );
  },

  entity(worldId: string, topicId: string, entityId: string): Promise<{
    ok: boolean;
    world: RpgWorldSummary;
    topic: RpgAuthoringTopic;
    entity: Record<string, unknown>;
    history: RpgAuthoringEntityHistory[];
  }> {
    return request(entityPath(worldId, topicId, entityId));
  },

  updateEntity(
    worldId: string,
    topicId: string,
    entityId: string,
    body: Record<string, unknown>,
  ): Promise<RpgAuthoringEntityMutationResponse> {
    return request(entityPath(worldId, topicId, entityId), jsonPatch(body));
  },

  regenerateEntity(
    worldId: string,
    topicId: string,
    entityId: string,
    body: Record<string, unknown>,
  ): Promise<RpgAuthoringEntityMutationResponse> {
    return request(`${entityPath(worldId, topicId, entityId)}/regenerate`, jsonPost(body));
  },

  updateEntityDossier(
    worldId: string,
    topicId: string,
    entityId: string,
    body: Record<string, unknown>,
  ): Promise<RpgAuthoringEntityMutationResponse> {
    return request(`${entityPath(worldId, topicId, entityId)}/dossier`, jsonPatch(body));
  },

  previewEntityDossier(
    worldId: string,
    topicId: string,
    entityId: string,
    body: Record<string, unknown>,
  ): Promise<RpgAuthoringDossierPreviewResponse> {
    return request(
      `${entityPath(worldId, topicId, entityId)}/regenerate-dossier-preview`,
      jsonPost(body),
    );
  },

  regenerateEntityDossier(
    worldId: string,
    topicId: string,
    entityId: string,
    body: Record<string, unknown>,
  ): Promise<RpgAuthoringEntityMutationResponse> {
    return request(`${entityPath(worldId, topicId, entityId)}/regenerate-dossier`, jsonPost(body));
  },
};
