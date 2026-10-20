import { omnixApiClient, type JobRecord } from '../../../api/client';
import { pipelineFetch } from '../../../api/fetchPipeline';
import { sendGatewayCall } from '../../../api/http';
import { api } from './gateway';
import type { components } from './generated';

export type DubProject = components['schemas']['DubProject'];
export type DubSegment = components['schemas']['DubSegment'];
export type DubProjectUpdate = components['schemas']['DubProjectUpdate'];
export type DubStep = 'ingest' | 'separate' | 'transcribe' | 'translate' | 'cast' | 'synthesize' | 'mux';

export const DUB_STEPS: { id: DubStep; label: string; resource: string }[] = [
  { id: 'ingest', label: 'Extract audio', resource: 'cpu' },
  { id: 'separate', label: 'Separate voices', resource: 'gpu:audio' },
  { id: 'transcribe', label: 'Transcribe', resource: 'gpu:stt' },
  { id: 'translate', label: 'Translate', resource: 'gpu:llm' },
  { id: 'cast', label: 'Cast voices', resource: 'cpu' },
  { id: 'synthesize', label: 'Speak and fit', resource: 'gpu:tts' },
  { id: 'mux', label: 'Mix and export', resource: 'cpu' },
];

export interface NewDub {
  file: File;
  title: string;
  sourceLanguage: string;
  targetLanguage: string;
  speakers: number;
  translator: string;
}

async function createError(response: Response): Promise<Error> {
  let detail = '';
  try {
    const body = (await response.json()) as { detail?: unknown };
    detail = typeof body.detail === 'string' ? body.detail : '';
  } catch {
    // Not JSON: the status says enough.
  }
  return new Error(`The video could not be uploaded (HTTP ${response.status}${detail ? `: ${detail}` : ''}).`);
}

export const dubbingClient = {
  async listProjects(): Promise<DubProject[]> {
    const data = await sendGatewayCall(() => api.GET('/api/dubbing/projects'));
    return data.projects;
  },

  async getProject(projectId: string): Promise<DubProject> {
    return sendGatewayCall(() => api.GET('/api/dubbing/projects/{project_id}', { params: { path: { project_id: projectId } } }));
  },

  /** Upload the video as the request body (it can be gigabytes) and create its project. */
  async createProject(dub: NewDub): Promise<DubProject> {
    const query = new URLSearchParams({
      filename: dub.file.name,
      title: dub.title,
      source_language: dub.sourceLanguage,
      target_language: dub.targetLanguage,
      speakers: String(dub.speakers),
      translator: dub.translator,
    });
    const response = await pipelineFetch(`/api/dubbing/projects?${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: dub.file,
    });
    if (!response.ok) throw await createError(response);
    return (await response.json()) as DubProject;
  },

  async updateProject(projectId: string, update: DubProjectUpdate): Promise<DubProject> {
    return sendGatewayCall(() => api.PATCH('/api/dubbing/projects/{project_id}', { params: { path: { project_id: projectId } }, body: update }));
  },

  async deleteProject(projectId: string): Promise<void> {
    await sendGatewayCall(() => api.DELETE('/api/dubbing/projects/{project_id}', { params: { path: { project_id: projectId } } }));
  },

  async updateLine(projectId: string, lineId: string, update: { translation?: string; voice_override?: string }): Promise<DubProject> {
    return sendGatewayCall(() => api.PUT('/api/dubbing/projects/{project_id}/lines/{line_id}', {
      params: { path: { project_id: projectId, line_id: lineId } }, body: update,
    }));
  },

  async approve(projectId: string, lineIds: string[], approve = true): Promise<DubProject> {
    return sendGatewayCall(() => api.POST('/api/dubbing/projects/{project_id}/approval', {
      params: { path: { project_id: projectId } }, body: { line_ids: lineIds, approve },
    }));
  },

  /** Run a step as a durable job; ``chain`` runs the following steps up to review. */
  async runStep(projectId: string, step: DubStep, options: { chain?: boolean; lineIds?: string[] } = {}): Promise<JobRecord> {
    const spec = DUB_STEPS.find((entry) => entry.id === step);
    return omnixApiClient.createJob({
      module: 'dubbing',
      type: `dub.${step}`,
      resource_class: (spec?.resource ?? 'cpu') as JobRecord['resource_class'],
      priority: 0,
      input_payload: { project_id: projectId, chain: Boolean(options.chain), line_ids: options.lineIds ?? [] },
    });
  },
};
