import { omnixApiClient, type JobListResponse } from '../../api/client';

const VOICE_JOB_SUMMARIES_PATH = '/api/jobs/voice-summaries?limit=40';

type VoiceJobListWindow = Window & typeof globalThis & {
  __omnixVoiceJobListGuardInstalled?: boolean;
};

export function installVoiceJobListGuard(): void {
  if (typeof window === 'undefined') return;
  const voiceWindow = window as VoiceJobListWindow;
  if (voiceWindow.__omnixVoiceJobListGuardInstalled) return;
  voiceWindow.__omnixVoiceJobListGuardInstalled = true;

  const originalListJobs = omnixApiClient.listJobs.bind(omnixApiClient);
  omnixApiClient.listJobs = async (): Promise<JobListResponse> => {
    if (!isVoiceStudioPath(window.location.pathname)) return originalListJobs();

    try {
      const response = await window.fetch(VOICE_JOB_SUMMARIES_PATH, {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error(`Voice job summaries failed with status ${response.status}.`);
      return await response.json() as JobListResponse;
    } catch (error) {
      console.error('[Voice Studio] Bounded job list unavailable; suppressing unbounded history load.', error);
      return { jobs: [] };
    }
  };
}

function isVoiceStudioPath(pathname: string): boolean {
  return pathname.replace(/\/+$/, '') === '/voice';
}

installVoiceJobListGuard();
