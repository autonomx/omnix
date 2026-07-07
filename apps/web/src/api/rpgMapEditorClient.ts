import { omnixApiClient } from './client';
import type { RpgMapDefinition } from './rpgMapClient';

export interface RpgMapContentIssue {
  code: string;
  detail: string;
  path: string;
  severity: 'error' | 'warning';
}

export interface RpgMapContentReport {
  canonical_json: string;
  issues: RpgMapContentIssue[];
  ok: boolean;
  revision: string;
}

export type RpgMapEditorOperation =
  | { type: 'move_object'; object_id: string; x: number; y: number }
  | { type: 'assign_object_asset'; object_id: string; asset_id: string; width: number; height: number }
  | { type: 'set_object_polygon'; object_id: string; field: 'footprint' | 'hitbox'; points: [number, number][] }
  | { type: 'set_child_map'; object_id: string; child_map_id: string | null }
  | { type: 'upsert_route'; route_id: string; points: [number, number][]; style: string }
  | { type: 'remove_route'; route_id: string }
  | { type: 'set_background_asset'; asset_id: string; source_crop?: Record<string, number> | null };

export interface RpgMapEditorContext {
  allowed_asset_ids?: string[];
  canonical_route_ids?: string[];
  known_map_ids?: string[];
}

export interface RpgMapValidationResponse {
  ok: boolean;
  report: RpgMapContentReport;
}

export interface RpgMapApplyResponse extends RpgMapValidationResponse {
  definition: RpgMapDefinition;
}

export function validateRpgMapDefinition(
  definition: RpgMapDefinition | Record<string, unknown>,
  context: RpgMapEditorContext = {},
): Promise<RpgMapValidationResponse> {
  return omnixApiClient.post(
    '/api/rpg/map-editor/validate',
    { definition, context },
  );
}

export function applyRpgMapEditorOperations(
  definition: RpgMapDefinition | Record<string, unknown>,
  operations: RpgMapEditorOperation[],
  context: RpgMapEditorContext = {},
): Promise<RpgMapApplyResponse> {
  return omnixApiClient.post(
    '/api/rpg/map-editor/apply',
    { definition, operations, context },
  );
}
