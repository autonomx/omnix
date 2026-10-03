import type { AssetListResponse, JobListResponse, JobRecord } from '../../api/client';
import type { components } from '../../api/generated/types';
import { api, unwrap } from '../../api/http';
import type { ImageModelStatusPayload } from './ImageModelControl';
import type { WorkerHealthPayload } from './imageReadinessModel';

type ImageModelDownloadRequest = components['schemas']['ImageModelDownloadRequest'];
export type ImageAssetDeleteResponse = components['schemas']['ImageAssetDeleteResponse'];

// The model routes drop unset fields; the image service always sends what the view reads.
const modelStatus = async (call: Promise<{ data?: unknown; error?: unknown; response: Response }>) =>
  (await unwrap(call)) as ImageModelStatusPayload;

/** The image workspace's gateway calls (WP-9.3). */
export const imageApi = {
  workerHealth: (): Promise<WorkerHealthPayload> => unwrap(api.GET('/api/workers/health')),
  modelStatus: (provider: string) =>
    modelStatus(api.GET('/api/image-generation/model/status', { params: { query: { provider } } })),
  downloadModel: (request: ImageModelDownloadRequest) =>
    modelStatus(api.POST('/api/image-generation/model/download', { body: request })),
  loadModel: (provider: string) => modelStatus(api.POST('/api/image-generation/model/load', { body: { provider } })),
  unloadModel: (provider: string) => modelStatus(api.POST('/api/image-generation/model/unload', { body: { provider } })),
  jobs: (): Promise<JobListResponse> => unwrap(api.GET('/api/image-generation/jobs')),
  retryJob: (jobId: string): Promise<JobRecord> =>
    unwrap(api.POST('/api/image-generation/jobs/{job_id}/retry', { params: { path: { job_id: jobId } } })),
  assets: (): Promise<AssetListResponse> => unwrap(api.GET('/api/image-generation/assets')),
  deleteAsset: (assetId: string): Promise<ImageAssetDeleteResponse> =>
    unwrap(api.POST('/api/image-generation/assets/{asset_id}/delete', { params: { path: { asset_id: assetId } } })),
};
