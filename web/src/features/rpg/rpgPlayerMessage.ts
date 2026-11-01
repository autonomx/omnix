import { ApiError } from '../../api/errors';

/** What a refused or failed call tells the player: the gateway's own message when it gave one, else ``fallback``. */
export function rpgPlayerMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body) as { detail?: unknown; message?: unknown };
      const detail = parsed.detail && typeof parsed.detail === 'object' ? parsed.detail as { message?: unknown } : parsed;
      if (typeof detail.message === 'string' && detail.message.trim()) return detail.message.trim();
    } catch {
      // A body that is not JSON says nothing for the player.
    }
    return fallback;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}
