import type { RpgAuthoringEntityCard } from './rpgWorldAuthoringClient';

export interface RpgCampaignLoreResponse {
  ok: boolean;
  session_id: string;
  canon_revision: number;
  content_hash: string;
  dossier_cards?: {
    characters?: RpgAuthoringEntityCard[];
    locations?: RpgAuthoringEntityCard[];
    factions?: RpgAuthoringEntityCard[];
  };
  topic_cards?: Record<string, RpgAuthoringEntityCard[]>;
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Campaign lore request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const rpgCampaignLoreClient = {
  read(sessionId: string): Promise<RpgCampaignLoreResponse> {
    return request<RpgCampaignLoreResponse>(
      `/api/rpg/sessions/${encodeURIComponent(sessionId)}/lore`,
    );
  },
};
