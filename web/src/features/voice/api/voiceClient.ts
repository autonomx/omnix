import { sendGatewayCall } from '../../../api/http';
import type { AssetListResponse, JobListResponse } from '../../../api/client';
import { api } from './gateway';

/** The voice feature's gateway calls: the voice library and voice job history (PA-2.4). */
export const voiceApiClient = {
  /** Voice Studio's bounded job history: recent voice and voice-cloning jobs only. */
  async listVoiceJobSummaries(limit = 40): Promise<JobListResponse> {
    return sendGatewayCall(() => api.GET('/api/jobs/voice-summaries', { params: { query: { limit } } }));
  },

  async listVoiceLibrary(): Promise<AssetListResponse> {
    return sendGatewayCall(() => api.GET('/api/voice-library'));
  },
};
