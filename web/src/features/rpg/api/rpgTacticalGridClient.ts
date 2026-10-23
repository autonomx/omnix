import { unwrap } from '../../../api/http';
import type { RpgGridView } from '../rpgTacticalGridModel';
import { api } from './gateway';

interface TacticalCommand {
  actorId: string;
  campaignRevision: number;
  mapStateRevision: number;
}

function commandIds(): { submission_id: string; command_id: string } {
  const id = crypto.randomUUID();
  return { submission_id: `grid:${id}`, command_id: `grid:${id}` };
}

/** A local map's tactical grid: what the player's character sees, and its moves and attacks. */
export const rpgTacticalGridClient = {
  /** Looks again (a no-op when nothing changed) and returns the projection with the player's tactical turn. */
  async observe(mapInstanceId: string, observerActorId: string): Promise<RpgGridView> {
    return await unwrap(api.POST('/api/rpg/map-instances/{map_instance_id}/observers/{observer_actor_id}/observe', {
      params: { path: { map_instance_id: mapInstanceId, observer_actor_id: observerActorId } },
      body: {},
    })) as unknown as RpgGridView;
  },

  async move(mapInstanceId: string, command: TacticalCommand & { destination: [number, number] }): Promise<unknown> {
    return await unwrap(api.POST('/api/rpg/map-instances/{map_instance_id}/tactical/move', {
      params: { path: { map_instance_id: mapInstanceId } },
      body: {
        ...commandIds(),
        actor_id: command.actorId,
        destination: command.destination,
        expected_campaign_revision: command.campaignRevision,
        expected_map_state_revision: command.mapStateRevision,
      },
    }));
  },

  async attack(mapInstanceId: string, command: TacticalCommand & { targetId: string }): Promise<unknown> {
    return await unwrap(api.POST('/api/rpg/map-instances/{map_instance_id}/tactical/attack', {
      params: { path: { map_instance_id: mapInstanceId } },
      body: {
        ...commandIds(),
        actor_id: command.actorId,
        target_id: command.targetId,
        expected_campaign_revision: command.campaignRevision,
        expected_map_state_revision: command.mapStateRevision,
      },
    }));
  },
};
