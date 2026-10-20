import { pipelineFetch } from '../../../api/fetchPipeline';
import { sendGatewayCall } from '../../../api/http';
import type { AssetListResponse, JobListResponse, JobRecord } from '../../../api/client';
import { api } from './gateway';
import type { components } from './generated';

export type TtsEnginesResponse = components['schemas']['TtsEnginesResponse'];
export type TtsEngineSwitchPhase = TtsEnginesResponse['switch']['phase'];
export type VoicePeaksResponse = components['schemas']['VoicePeaksResponse'];
export type VoiceScript = components['schemas']['VoiceScript'];
export type VoiceScriptSummary = components['schemas']['VoiceScriptSummary'];
export type VoiceScriptLine = components['schemas']['VoiceScriptLine'];
export type VoiceTake = components['schemas']['VoiceTake'];
export type VoiceScriptWrite = components['schemas']['VoiceScriptWrite'];
export type SpeechModelListResponse = components['schemas']['SpeechModelListResponse'];
export type SpeechModelStatus = components['schemas']['SpeechModelStatus'];
export type TranscriptResponse = components['schemas']['TranscriptResponse'];
export type SpeakerSample = components['schemas']['SpeakerSample'];
export type AudioToolsStatus = components['schemas']['AudioToolsStatus'];
export type TranscriptExportFormat = 'srt' | 'vtt' | 'txt' | 'json';
export type Recipe = components['schemas']['Recipe'];
export type RecipeStep = components['schemas']['RecipeStep'];
export type RecipeList = components['schemas']['RecipeList'];
export type BatchRun = components['schemas']['BatchRun'];
export type BatchItem = components['schemas']['BatchItem'];
export type ClientCredential = components['schemas']['ClientCredential'];
export type ClientCredentialList = components['schemas']['ClientCredentialList'];
export type Dictation = components['schemas']['Dictation'];

async function exportError(response: Response): Promise<Error> {
  let detail = '';
  try {
    const parsed = (await response.json()) as { detail?: unknown };
    detail = typeof parsed.detail === 'string' ? parsed.detail : '';
  } catch {
    // A body that is not JSON keeps the status alone.
  }
  return new Error(`The transcript could not be exported (HTTP ${response.status}${detail ? `: ${detail}` : ''}).`);
}

/** The voice feature's gateway calls: the voice library and voice job history (PA-2.4). */
export const voiceApiClient = {
  /** Voice Studio's bounded job history: recent voice and voice-cloning jobs only. */
  async listVoiceJobSummaries(limit = 40): Promise<JobListResponse> {
    return sendGatewayCall(() => api.GET('/api/jobs/voice-summaries', { params: { query: { limit } } }));
  },

  async listVoiceLibrary(): Promise<AssetListResponse> {
    return sendGatewayCall(() => api.GET('/api/voice-library'));
  },

  /** The local TTS engines, which one Omnix uses, and the progress of the last switch. */
  async listTtsEngines(): Promise<TtsEnginesResponse> {
    return sendGatewayCall(() => api.GET('/api/tts/engines'));
  },

  /** Make an engine Omnix's default TTS; the old one unloads and the new one loads in the background. */
  async selectTtsEngine(providerId: string): Promise<TtsEnginesResponse> {
    return sendGatewayCall(() => api.POST('/api/tts/engines/select', { body: { provider_id: providerId } }));
  },

  /** Peaks of a stored WAV take, drawn by the transport bar's waveform. */
  async getTakePeaks(assetId: string, bins = 480): Promise<VoicePeaksResponse> {
    return sendGatewayCall(() => api.GET('/api/voice/assets/{asset_id}/peaks', { params: { path: { asset_id: assetId }, query: { bins } } }));
  },

  /** Saved scripts, most recently edited first. */
  async listScripts(): Promise<{ scripts: VoiceScriptSummary[] }> {
    return sendGatewayCall(() => api.GET('/api/voice/scripts'));
  },

  async getScript(scriptId: string): Promise<VoiceScript> {
    return sendGatewayCall(() => api.GET('/api/voice/scripts/{script_id}', { params: { path: { script_id: scriptId } } }));
  },

  async createScript(write: VoiceScriptWrite): Promise<VoiceScript> {
    return sendGatewayCall(() => api.POST('/api/voice/scripts', { body: write }));
  },

  /** Save edits; unchanged lines keep their id and takes. A stale revision answers 409. */
  async updateScript(scriptId: string, write: VoiceScriptWrite): Promise<VoiceScript> {
    return sendGatewayCall(() => api.PUT('/api/voice/scripts/{script_id}', { params: { path: { script_id: scriptId } }, body: write }));
  },

  async deleteScript(scriptId: string): Promise<void> {
    await sendGatewayCall(() => api.DELETE('/api/voice/scripts/{script_id}', { params: { path: { script_id: scriptId } } }));
  },

  async selectTake(scriptId: string, lineId: string, takeId: string): Promise<VoiceScript> {
    return sendGatewayCall(() => api.POST('/api/voice/scripts/{script_id}/lines/{line_id}/takes/{take_id}/select', {
      params: { path: { script_id: scriptId, line_id: lineId, take_id: takeId } },
    }));
  },

  async pinTake(takeId: string, pinned: boolean): Promise<void> {
    await sendGatewayCall(() => api.POST('/api/voice/takes/{take_id}/pin', { params: { path: { take_id: takeId } }, body: { pinned } }));
  },

  /** Speech models Omnix can install, with licences and whether their weights are present. */
  async listSpeechModels(): Promise<SpeechModelListResponse> {
    return sendGatewayCall(() => api.GET('/api/voice/models'));
  },

  /** Store or clear the Hugging Face token (workspace admins). */
  async saveHubToken(token: string): Promise<SpeechModelListResponse> {
    return sendGatewayCall(() => api.PUT('/api/voice/models/hub-token', { body: { token } }));
  },

  /** A transcript as an omnix-transcript-v1 document, with the revision a save must name. */
  async getTranscript(assetId: string): Promise<TranscriptResponse> {
    return sendGatewayCall(() => api.GET('/api/voice/transcripts/{asset_id}', { params: { path: { asset_id: assetId } } }));
  },

  /** Save an edited transcript as its next revision; a stale revision answers 409. */
  async saveTranscript(assetId: string, document: TranscriptResponse['document'], expectedRevision: number): Promise<TranscriptResponse> {
    return sendGatewayCall(() => api.PUT('/api/voice/transcripts/{asset_id}', {
      params: { path: { asset_id: assetId } }, body: { document, expected_revision: expectedRevision },
    }));
  },

  /** A speaker's cleanest 10-30 s from the source recording, ready to clone. */
  async speakerSample(assetId: string, speaker: string): Promise<SpeakerSample> {
    return sendGatewayCall(() => api.POST('/api/voice/transcripts/{asset_id}/speaker-sample', {
      params: { path: { asset_id: assetId } }, body: { speaker },
    }));
  },

  /** The transcript as subtitles, text or JSON, with the file name the gateway suggests. */
  async exportTranscript(assetId: string, format: TranscriptExportFormat): Promise<{ blob: Blob; filename: string }> {
    const response = await pipelineFetch(`/api/voice/transcripts/${encodeURIComponent(assetId)}/export?format=${format}`);
    if (!response.ok) throw await exportError(response);
    const match = response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i);
    return { blob: await response.blob(), filename: match?.[1]?.trim() || `transcript.${format}` };
  },

  /** The audio service: whether it answers, which tools work, and whether renders are watermarked. */
  async audioToolsStatus(): Promise<AudioToolsStatus> {
    return sendGatewayCall(() => api.GET('/api/voice/audio-tools'));
  },

  /** Turn render watermarking on or off for the workspace (workspace admins). */
  async saveWatermark(enabled: boolean): Promise<{ enabled: boolean }> {
    return sendGatewayCall(() => api.PUT('/api/voice/watermark', { body: { enabled } }));
  },

  /** Recipes, newest first, and the tools a step can use. */
  async listRecipes(): Promise<RecipeList> {
    return sendGatewayCall(() => api.GET('/api/voice/recipes'));
  },

  /** Create a recipe, or change one (changed steps make a new version). */
  async saveRecipe(write: { name: string; steps: RecipeStep[] }, recipeId?: string): Promise<Recipe> {
    if (recipeId) {
      return sendGatewayCall(() => api.PUT('/api/voice/recipes/{recipe_id}', { params: { path: { recipe_id: recipeId } }, body: write }));
    }
    return sendGatewayCall(() => api.POST('/api/voice/recipes', { body: write }));
  },

  async deleteRecipe(recipeId: string): Promise<void> {
    await sendGatewayCall(() => api.DELETE('/api/voice/recipes/{recipe_id}', { params: { path: { recipe_id: recipeId } } }));
  },

  /** Batch runs, newest first (without their items). */
  async listBatches(): Promise<{ runs: BatchRun[] }> {
    return sendGatewayCall(() => api.GET('/api/voice/batches'));
  },

  async getBatch(runId: string): Promise<BatchRun> {
    return sendGatewayCall(() => api.GET('/api/voice/batches/{run_id}', { params: { path: { run_id: runId } } }));
  },

  /** Run a recipe over stored recordings: one item each, skipped when done before at this recipe version. */
  async startBatch(recipeId: string, assetIds: string[], title = ''): Promise<BatchRun> {
    return sendGatewayCall(() => api.POST('/api/voice/batches', { body: { recipe_id: recipeId, asset_ids: assetIds, title } }));
  },

  async cancelBatch(runId: string): Promise<BatchRun> {
    return sendGatewayCall(() => api.POST('/api/voice/batches/{run_id}/cancel', { params: { path: { run_id: runId } } }));
  },

  /** API clients (MCP and `/api/voice/v1`) of this workspace; workspace admins only. */
  async listClients(): Promise<ClientCredentialList> {
    return sendGatewayCall(() => api.GET('/api/voice/clients'));
  },

  /** Issue a client credential; its token is in this answer only. */
  async issueClient(name: string, capabilities: string[], expiresInDays: number | null): Promise<ClientCredential> {
    return sendGatewayCall(() => api.POST('/api/voice/clients', { body: { name, capabilities, expires_in_days: expiresInDays } }));
  },

  async revokeClient(clientId: string): Promise<{ revoked: boolean }> {
    return sendGatewayCall(() => api.DELETE('/api/voice/clients/{client_id}', { params: { path: { client_id: clientId } } }));
  },

  /** Load the batch speech-to-text engine ahead of a dictation. */
  async warmDictation(): Promise<{ ready: boolean; detail?: string }> {
    return sendGatewayCall(() => api.POST('/api/voice/dictate/warm'));
  },

  /** Transcribe a short push-to-talk recording with the batch engine (any supported language). */
  async dictate(audio: Blob, language = ''): Promise<Dictation> {
    const form = new FormData();
    const extension = audio.type.includes('ogg') ? 'ogg' : audio.type.includes('mp4') ? 'm4a' : 'webm';
    form.append('file', audio, `dictation.${extension}`);
    if (language) form.append('language', language);
    const response = await pipelineFetch('/api/voice/dictate', { method: 'POST', body: form });
    if (!response.ok) {
      let detail = '';
      try {
        const parsed = (await response.json()) as { detail?: unknown };
        detail = typeof parsed.detail === 'string' ? parsed.detail : '';
      } catch {
        // A body that is not JSON keeps the status alone.
      }
      throw new Error(detail || `Dictation failed (HTTP ${response.status}).`);
    }
    return (await response.json()) as Dictation;
  },

  /** Queue a fresh copy of a failed or cancelled job. */
  async retryJob(jobId: string): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/jobs/{job_id}/retry', { params: { path: { job_id: jobId } } })) as Promise<JobRecord>;
  },
};
