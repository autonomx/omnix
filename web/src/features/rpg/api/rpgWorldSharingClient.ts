import { unwrap } from '../../../api/http';
import { api } from './gateway';
import type { components } from './generated';

export type RpgWorldCatalog = components['schemas']['RpgWorldCatalogResponse'];
export type RpgWorldCatalogEntry = components['schemas']['RpgWorldCatalogEntry'];
export type RpgWorldCatalogInstall = components['schemas']['RpgWorldCatalogInstallResponse'];
export type RpgSharedWorldState = components['schemas']['RpgSharedWorldStateResponse'];
export type RpgWorldAdoption = components['schemas']['RpgWorldAdoptionResponse'];
export type RpgWorldSharingStatus = components['schemas']['RpgWorldSharingStatusResponse'];
export type RpgGitHubDeviceSignIn = components['schemas']['RpgGitHubDeviceSignInResponse'];
export type RpgWorldShare = components['schemas']['RpgWorldShareResponse'];

export function catalogCoverUrl(entryId: string): string {
  return `/api/rpg/world-catalog/${encodeURIComponent(entryId)}/cover`;
}

/** Community worlds: the catalog on GitHub, adopting a downloaded world, and sharing your own by pull request. */
export const rpgWorldSharingClient = {
  async catalog(): Promise<RpgWorldCatalog> {
    return await unwrap(api.GET('/api/rpg/world-catalog'));
  },

  async install(entryId: string): Promise<RpgWorldCatalogInstall> {
    return await unwrap(api.POST('/api/rpg/world-catalog/{entry_id}/install', { params: { path: { entry_id: entryId } } }));
  },

  async sharedState(worldId: string): Promise<RpgSharedWorldState> {
    return await unwrap(api.GET('/api/rpg/worlds/{world_id}/shared', { params: { path: { world_id: worldId } } }));
  },

  async adopt(worldId: string, bundleSha256: string): Promise<RpgWorldAdoption> {
    return await unwrap(api.POST('/api/rpg/worlds/{world_id}/adopt', {
      params: { path: { world_id: worldId } },
      body: { bundle_sha256: bundleSha256 },
    }));
  },

  async share(worldId: string, summary: string): Promise<RpgWorldShare> {
    return await unwrap(api.POST('/api/rpg/worlds/{world_id}/share', {
      params: { path: { world_id: worldId } },
      body: { summary },
    }));
  },

  async gitHubStatus(): Promise<RpgWorldSharingStatus> {
    return await unwrap(api.GET('/api/rpg/world-sharing/github'));
  },

  async connectWithToken(token: string): Promise<RpgWorldSharingStatus> {
    return await unwrap(api.PUT('/api/rpg/world-sharing/github/token', { body: { token } }));
  },

  async startDeviceSignIn(): Promise<RpgGitHubDeviceSignIn> {
    return await unwrap(api.POST('/api/rpg/world-sharing/github/device'));
  },

  async pollDeviceSignIn(flowId: string): Promise<RpgWorldSharingStatus> {
    return await unwrap(api.POST('/api/rpg/world-sharing/github/device/{flow_id}/poll', { params: { path: { flow_id: flowId } } }));
  },

  async disconnect(): Promise<RpgWorldSharingStatus> {
    return await unwrap(api.DELETE('/api/rpg/world-sharing/github'));
  },
};
