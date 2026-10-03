import type { components } from '../../../api/generated/types';
import { api, unwrapAs } from '../../../api/http';

export type CharacterHermesSyncStatus = components['schemas']['CharacterHermesSyncStatus'];

const failure = (action: string) => (error: { body: string; status: number }) =>
  error.body || `Character Hermes ${action} failed with status ${error.status}.`;

export const characterHermesClient = {
  import(characterId: string): Promise<CharacterHermesSyncStatus> {
    return unwrapAs(api.POST('/api/characters/{character_id}/hermes/import', { params: { path: { character_id: characterId } } }), failure('import'));
  },
  export(characterId: string): Promise<CharacterHermesSyncStatus> {
    return unwrapAs(api.POST('/api/characters/{character_id}/hermes/export', { params: { path: { character_id: characterId } } }), failure('export'));
  },
};
