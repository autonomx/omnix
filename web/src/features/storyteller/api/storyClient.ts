import { sendGatewayCall, unwrap } from '../../../api/http';
import { api } from './gateway';
import type { components } from './generated';

export type StoryProject = components['schemas']['StoryProject'];
export type StoryProjectSummary = components['schemas']['StoryProjectSummary'];
export type StoryProjectCreate = components['schemas']['StoryProjectCreate'];
export type StoryProjectUpdate = components['schemas']['StoryProjectUpdate'];
export type StoryPage = components['schemas']['StoryPage'];
export type StoryBlock = components['schemas']['StoryBlock'];
export type StoryCharacter = components['schemas']['StoryCharacter'];
export type StoryCharacterInput = components['schemas']['StoryCharacter-Input'];
export type StoryNote = components['schemas']['StoryNote'];
export type StoryNoteInput = components['schemas']['StoryNoteInput'];
export type StoryVersionSummary = components['schemas']['StoryVersionSummary'];
export type StoryVersion = components['schemas']['StoryVersion'];
export type StorySelection = components['schemas']['StorySelection'];
export type StoryMove = components['schemas']['StoryMove'];
export type StoryImportItem = components['schemas']['StoryImportItem'];
export type StoryImportResult = components['schemas']['StoryImportResult'];
export type StoryVoiceCast = components['schemas']['StoryVoiceCast'];
export type StoryCastVoice = components['schemas']['StoryCastVoice'];
export type StoryOutlineChapter = components['schemas']['StoryOutlineChapter'];
export type StoryOutlineChapterInput = components['schemas']['StoryOutlineChapterInput'];
export type StoryExportFormat = 'epub' | 'docx' | 'pdf';

const project = (projectId: string) => ({ params: { path: { project_id: projectId } } });

/** The storyteller's gateway calls (PA-2.4): story projects with their pages, versions and trash (ST-1.2). */
export const storyApiClient = {
  async listProjects(trashed = false): Promise<StoryProjectSummary[]> {
    const listed = await sendGatewayCall(() => api.GET('/api/story/projects', { params: { query: { trashed } } }));
    return listed.projects;
  },
  async getProject(projectId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.GET('/api/story/projects/{project_id}', project(projectId)));
  },
  async createProject(body: StoryProjectCreate): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects', { body }));
  },
  async updateProject(projectId: string, body: StoryProjectUpdate): Promise<StoryProject> {
    return sendGatewayCall(() => api.PATCH('/api/story/projects/{project_id}', { ...project(projectId), body }));
  },
  async trashProject(projectId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/trash', project(projectId)));
  },
  async restoreProject(projectId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/restore', project(projectId)));
  },
  async purgeProject(projectId: string): Promise<void> {
    await sendGatewayCall(() => api.DELETE('/api/story/projects/{project_id}', project(projectId)));
  },
  /** Keeps the manuscript as a version; `kept_run` keeps an interactive run as a finished story (ST-3.6). */
  async saveVersion(projectId: string, title = '', kind: 'manual' | 'kept_run' = 'manual'): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/versions', { ...project(projectId), body: { title, kind } }));
  },
  /** Takes back the player's last move; its page stays as a branch (ST-3.4). */
  async undoMove(projectId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/undo', project(projectId)));
  },
  /** Makes the run that ends at a page the story: back to an earlier move, or another branch (ST-3.4). */
  async openPage(projectId: string, pageId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/pages/{page_id}/open', {
      params: { path: { project_id: projectId, page_id: pageId } },
    }));
  },
  /** Replaces a page's blocks as the writer edited them (ST-6.1); the page keeps its id and place. */
  /** A page's new blocks; the server refuses them when the page no longer holds `baseBlocks` (ST-6.1). */
  async updatePage(projectId: string, pageId: string, blocks: StoryBlock[], baseBlocks: StoryBlock[]): Promise<StoryProject> {
    return sendGatewayCall(() => api.PATCH('/api/story/projects/{project_id}/pages/{page_id}', {
      params: { path: { project_id: projectId, page_id: pageId } }, body: { blocks, base_blocks: baseBlocks },
    }));
  },
  /** A version with its pages, to compare (ST-6.3). */
  async getVersion(projectId: string, versionId: string): Promise<StoryVersion> {
    return sendGatewayCall(() => api.GET('/api/story/projects/{project_id}/versions/{version_id}', {
      params: { path: { project_id: projectId, version_id: versionId } },
    }));
  },
  /** Makes the change a selection version proposes (ST-6.2); a page changed since is a 409. */
  async acceptSelection(projectId: string, versionId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/versions/{version_id}/accept', {
      params: { path: { project_id: projectId, version_id: versionId } },
    }));
  },
  async rejectSelection(projectId: string, versionId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/versions/{version_id}/reject', {
      params: { path: { project_id: projectId, version_id: versionId } },
    }));
  },
  async restoreVersion(projectId: string, versionId: string): Promise<StoryProject> {
    return sendGatewayCall(() => api.POST('/api/story/projects/{project_id}/versions/{version_id}/restore', {
      params: { path: { project_id: projectId, version_id: versionId } },
    }));
  },
  /** Replaces the cast whole: a suggestion the writer has not accepted is sent back with `suggested: true`. */
  async replaceCharacters(projectId: string, characters: StoryCharacterInput[]): Promise<StoryProject> {
    return sendGatewayCall(() => api.PUT('/api/story/projects/{project_id}/characters', { ...project(projectId), body: { characters } }));
  },
  async replaceNotes(projectId: string, notes: StoryNoteInput[]): Promise<StoryProject> {
    return sendGatewayCall(() => api.PUT('/api/story/projects/{project_id}/notes', { ...project(projectId), body: { notes } }));
  },
  /** Replaces the plan whole (ST-5.1): a beat sent with its id keeps it, and the page drafted from it. */
  async replaceOutline(projectId: string, chapters: StoryOutlineChapterInput[]): Promise<StoryProject> {
    return sendGatewayCall(() => api.PUT('/api/story/projects/{project_id}/outline', { ...project(projectId), body: { chapters } }));
  },
  /** The story as a book file (ST-6.5), with the file name the server gave it. */
  async exportBook(projectId: string, format: StoryExportFormat): Promise<{ blob: Blob; fileName: string }> {
    let fileName = `story.${format}`;
    const blob = await unwrap(api.GET('/api/story/projects/{project_id}/export/{export_format}', {
      params: { path: { project_id: projectId, export_format: format } },
      parseAs: 'blob',
    }).then((result) => {
      fileName = /filename="([^"]+)"/.exec(result.response.headers.get('Content-Disposition') ?? '')?.[1] ?? fileName;
      return result;
    }));
    return { blob: blob as Blob, fileName };
  },
  async importStories(items: StoryImportItem[]): Promise<StoryImportResult> {
    return sendGatewayCall(() => api.POST('/api/story/projects/import', { body: { items } }));
  },
  /** The narrator's and each character's voice, cast on first ask, and the voices that can be chosen (ST-4.2). */
  async voiceCast(projectId: string): Promise<StoryVoiceCast> {
    return sendGatewayCall(() => api.GET('/api/story/projects/{project_id}/voices', project(projectId)));
  },
  async chooseVoice(projectId: string, speakerId: string, voiceId: string): Promise<StoryVoiceCast> {
    return sendGatewayCall(() => api.PUT('/api/story/projects/{project_id}/voices/{speaker_id}', {
      params: { path: { project_id: projectId, speaker_id: speakerId } },
      body: { voice_id: voiceId },
    }));
  },
};
