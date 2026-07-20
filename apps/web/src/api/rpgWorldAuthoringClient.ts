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

export interface RpgAuthoringManifestResponse {
  ok: boolean;
  world: RpgWorldSummary;
  sections: RpgAuthoringSection[];
  generation: RpgWorldGenerationRun | Record<string, never>;
}

export interface RpgAuthoringEntityCard {
  id: string;
  title: string;
  summary: string;
  kind: string;
  image_target_id?: string;
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

export const rpgWorldAuthoringClient = {
  manifest(worldId: string): Promise<RpgAuthoringManifestResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/authoring-manifest`);
  },

  section(worldId: string, sectionId: string): Promise<RpgAuthoringPage> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/authoring-sections/${encodeURIComponent(sectionId)}`,
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
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
  },
};
