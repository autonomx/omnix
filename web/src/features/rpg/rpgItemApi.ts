import type { ApiRequestOptions } from '../../api/client';
import { unwrap } from '../../api/http';
import { api } from './api/gateway';
import type { components } from './api/generated';
import type { RpgLaunchResponse } from './api/rpgSessionClient';

/** The compatibility route's envelope: a launch response with the action's own fields. */
export type RpgItemCompatResponse = components['schemas']['RpgCompatibilityResponse'] & RpgLaunchResponse;

export interface RpgItemApiClient {
  post<TRequest, TResponse>(path: `/api/${string}`, body: TRequest, options?: ApiRequestOptions): Promise<TResponse>;
}

/** An ability's detail comes from the compatibility route; this sends it with the typed gateway client. */
export const rpgItemGatewayClient: RpgItemApiClient = {
  async post<TRequest, TResponse>(path: `/api/${string}`, body: TRequest): Promise<TResponse> {
    if (path !== '/api/rpg/session/get') {
      throw new Error(`RPG ability details use /api/rpg/session/get, not ${path}`);
    }
    return await unwrap(api.POST('/api/rpg/session/get', {
      body: body as components['schemas']['RpgCompatibilityRequest'],
    })) as TResponse;
  },
};

export interface RpgAbilityDetailOptions {
  abilityName: string;
  abilityId?: string;
  source?: string;
}

export function fetchRpgAbilityDetails(
  sessionId: string,
  options: RpgAbilityDetailOptions,
  client: RpgItemApiClient = rpgItemGatewayClient,
): Promise<RpgItemCompatResponse> {
  return postRpgSessionGet(
    {
      action: 'ability_detail',
      session_id: sessionId,
      ability_name: options.abilityName,
      ability_id: options.abilityId,
      source: options.source ?? 'rpg-hotbar-tooltip',
    },
    client,
  );
}

function postRpgSessionGet(
  body: Record<string, unknown>,
  client: RpgItemApiClient,
): Promise<RpgItemCompatResponse> {
  return client.post<Record<string, unknown>, RpgItemCompatResponse>('/api/rpg/session/get', stripUndefined(body));
}

function stripUndefined(body: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined));
}
