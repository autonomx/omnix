export interface CharacterHermesSyncStatus {
  enabled: boolean;
  available: boolean;
  character_id: string;
  memory_dir: string;
  imported_candidate_ids: string[];
  exported_memory_ids: string[];
  skipped_reasons: string[];
}

async function run(characterId: string, action: 'import' | 'export'): Promise<CharacterHermesSyncStatus> {
  const response = await fetch(
    `/api/characters/${encodeURIComponent(characterId)}/hermes/${action}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Character Hermes ${action} failed with status ${response.status}.`);
  }
  return response.json() as Promise<CharacterHermesSyncStatus>;
}

export const characterHermesClient = {
  import(characterId: string): Promise<CharacterHermesSyncStatus> {
    return run(characterId, 'import');
  },
  export(characterId: string): Promise<CharacterHermesSyncStatus> {
    return run(characterId, 'export');
  },
};
