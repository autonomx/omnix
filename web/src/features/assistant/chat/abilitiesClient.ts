import type { components } from '../api/generated';
import { unwrapAs } from '../../../api/http';
import { api } from '../api/gateway';

export type OwnerAbilities = components['schemas']['OwnerAbilitiesPayload'];

function abilities(call: Promise<{ data?: OwnerAbilities; error?: unknown; response: Response }>): Promise<OwnerAbilities> {
  return unwrapAs(call, (error) => `Abilities request failed with status ${error.status}.`);
}

/** What a character or the System Assistant may use in calls; the person sets each one, nothing else does. */
export const abilitiesClient = {
  read(ownerId: string): Promise<OwnerAbilities> {
    return abilities(api.GET('/api/assistant/tools/abilities/{owner_id}', { params: { path: { owner_id: ownerId } } }));
  },
  set(ownerId: string, abilityId: string, granted: boolean): Promise<OwnerAbilities> {
    return abilities(api.PUT('/api/assistant/tools/abilities/{owner_id}/{ability_id}', {
      params: { path: { owner_id: ownerId, ability_id: abilityId } },
      body: { granted },
    }));
  },
};
