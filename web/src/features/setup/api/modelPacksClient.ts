import type { JobRecord } from '../../../api/client';
import { omnixApiClient } from '../../../api/client';
import { sendGatewayCall } from '../../../api/http';
import { api } from './gateway';
import type { components } from './generated';

export type ModelPacksStatus = components['schemas']['ModelPacksStatus'];
export type PackVerdict = components['schemas']['PackVerdict'];
export type PackRuntimeStatus = components['schemas']['PackRuntimeStatus'];
export type PackModelStatus = components['schemas']['PackModelStatus'];
export type SelectionSize = components['schemas']['SelectionSize'];
export type CapabilitiesResponse = components['schemas']['CapabilitiesResponse'];
export type PackTarget = components['schemas']['PackTarget'];

export const MODEL_PACKS_QUERY_KEY = ['setup', 'model-packs'] as const;
export const CAPABILITIES_QUERY_KEY = ['setup', 'capabilities'] as const;

/** The setup screen's gateway calls (desktop roadmap §4.5). */
export const modelPacksClient = {
  async status(): Promise<ModelPacksStatus> {
    return sendGatewayCall(() => api.GET('/api/model-packs'));
  },

  async selection(bundles: string[]): Promise<SelectionSize> {
    return sendGatewayCall(() => api.POST('/api/model-packs/selection', { body: { bundles } }));
  },

  async capabilities(): Promise<CapabilitiesResponse> {
    return sendGatewayCall(() => api.GET('/api/model-packs/capabilities'));
  },

  async install(target: PackTarget): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/model-packs/install', { body: target })) as Promise<JobRecord>;
  },

  async remove(target: PackTarget): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/model-packs/remove', { body: target })) as Promise<JobRecord>;
  },

  async verify(target: PackTarget): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/model-packs/verify', { body: target })) as Promise<JobRecord>;
  },

  async job(jobId: string): Promise<JobRecord> {
    return omnixApiClient.getJob(jobId);
  },

  async cancel(jobId: string): Promise<JobRecord> {
    return omnixApiClient.cancelJob(jobId, 'cancelled from the setup screen');
  },
};

/** `bytes` as GB with one decimal (the units the setup screen and the roadmap use). */
export function formatGigabytes(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}
