import { omnixApiClient } from '../../api/client';
import { podcastDefaults } from '../settings/moduleDefaults';
import { loadSettingsProfile } from '../settings/settingsApi';

const INSTALLED_KEY = '__omnix_podcast_session_guard__';

type AnyWindow = Window & Record<string, unknown>;

type ClientPatch = {
  createChatSession: typeof omnixApiClient.createChatSession;
};

function isPodcastDraftTitle(title: unknown): boolean {
  return String(title ?? '').trim().startsWith('Podcast script:');
}

export function installPodcastSessionGuard(): void {
  if (typeof window === 'undefined') return;
  const w = window as unknown as AnyWindow;
  if (w[INSTALLED_KEY]) return;
  w[INSTALLED_KEY] = true;

  const client = omnixApiClient as unknown as ClientPatch;
  const originalCreate = client.createChatSession.bind(omnixApiClient);

  client.createChatSession = async (request) => {
    if (!isPodcastDraftTitle(request.title)) return originalCreate(request);
    try {
      const { profile } = await loadSettingsProfile();
      const defaults = podcastDefaults(profile);
      return originalCreate({
        ...request,
        provider_id: request.provider_id || defaults.providerId || undefined,
        model_id: request.model_id || defaults.modelId || undefined,
      });
    } catch {
      return originalCreate(request);
    }
  };
}

installPodcastSessionGuard();
