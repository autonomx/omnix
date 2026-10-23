/**
 * Which browser permissions the app's windows get (desktop roadmap DT-4.2): notifications and clipboard writes, and
 * the microphone (audio only, never the camera) for the gateway's own pages. Everything else is refused, and so is
 * the microphone for any other origin.
 */
export function allowPermission(permission: string, requestingUrl: string, origin: string | null,
                                mediaTypes: readonly string[] = []): boolean {
  if (permission === 'notifications' || permission === 'clipboard-sanitized-write') return true;
  if (permission !== 'media') return false;
  if (!origin) return false;
  let requesting: string;
  try {
    requesting = new URL(requestingUrl).origin;
  } catch {
    return false;
  }
  if (requesting !== origin) return false;
  return mediaTypes.length > 0 && mediaTypes.every((type) => type === 'audio');
}
