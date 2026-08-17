import type { OmnixModeId } from '../app/omnixModeIds';
import { toBackendModeId } from '../app/modeNameMap';
import { omnixApiClient } from './client';

export interface ModeMetadataResponse {
  ok?: boolean;
  read_only?: boolean;
  executes?: boolean;
  route?: Record<string, unknown>;
  routes?: Array<Record<string, unknown>>;
  error?: string | null;
}

export function modeMetadataPath(mode?: OmnixModeId): `/api/${string}` {
  return mode
    ? `/api/modes/metadata?mode=${encodeURIComponent(toBackendModeId(mode))}`
    : '/api/modes/metadata';
}

export function getModeMetadata(mode?: OmnixModeId): Promise<ModeMetadataResponse> {
  return omnixApiClient.get<ModeMetadataResponse>(modeMetadataPath(mode));
}
