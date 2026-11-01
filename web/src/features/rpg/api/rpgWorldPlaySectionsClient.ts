import { pipelineFetch } from '../../../api/fetchPipeline';

import type { components } from './generated';

/** How a world plays, in the world editor (RQ-4.1): the author's draft, its readiness and what it may name. */
export type RpgPlaySectionsResponse = components['schemas']['RpgPlaySectionsResponse'];
export type RpgPlaySectionsDraft = components['schemas']['PlaySectionsDraft'];
export type RpgPlaySectionsReferences = components['schemas']['RpgPlaySectionsReferences'];
export type RpgPlaySectionsReadiness = components['schemas']['RpgPlaySectionsReadiness'];

/** A refused request: its status, its error code and, for a draft of the wrong shape, each error. */
export class RpgPlaySectionsError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly findings: string[],
  ) {
    super(code || `Request failed with status ${status}`);
    this.name = 'RpgPlaySectionsError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await pipelineFetch(path, init);
  const text = await response.text();
  if (!response.ok) {
    let detail: { error?: unknown; findings?: unknown } = {};
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      detail = parsed.detail && typeof parsed.detail === 'object' ? parsed.detail as typeof detail : { error: parsed.detail };
    } catch {
      detail = { error: text };
    }
    const findings = Array.isArray(detail.findings) ? detail.findings.map(String) : [];
    throw new RpgPlaySectionsError(response.status, typeof detail.error === 'string' ? detail.error : '', findings);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

function sectionsPath(worldId: string, suffix = ''): string {
  return `/api/rpg/worlds/${encodeURIComponent(worldId)}/play-sections${suffix}`;
}

export const rpgWorldPlaySectionsClient = {
  read(worldId: string): Promise<RpgPlaySectionsResponse> {
    return request(sectionsPath(worldId));
  },

  save(worldId: string, expectedContentHash: string, document: RpgPlaySectionsDraft): Promise<RpgPlaySectionsResponse> {
    return request(sectionsPath(worldId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_content_hash: expectedContentHash, document }),
    });
  },

  draftFromLore(worldId: string): Promise<{ ok: boolean; world_id: string; document: RpgPlaySectionsDraft }> {
    return request(sectionsPath(worldId, '/draft-from-lore'), { method: 'POST' });
  },

  publish(worldId: string): Promise<RpgPlaySectionsResponse> {
    return request(sectionsPath(worldId, '/publish'), { method: 'POST' });
  },
};
