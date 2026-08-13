export const LIVE_STT_SPECULATION_PARTIAL_EVENT = 'omnix:live-stt-speculation-partial';
export const LIVE_STT_SPECULATION_CANDIDATE_EVENT = 'omnix:live-stt-speculation-candidate';
export const LIVE_STT_SPECULATION_FINAL_EVENT = 'omnix:live-stt-speculation-final';
export const LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT = 'omnix:live-stt-speculation-delivery-settled';

const DEFAULT_ENDPOINT_THRESHOLD = 0.75;

export type AuthorityMode = 'observational' | 'test' | 'auto';

type AuthorityResponse = {
  eligible?: boolean;
  ok?: boolean;
  reasons?: string[];
  mode?: string;
};

export type AuthoritySelection = {
  websocketUrl: string;
  authorityEnabled: boolean;
  mode: AuthorityMode;
  endpointThreshold: number;
  fallbackUsed: boolean;
  reasons: string[];
};

export async function resolveAuthoritySelection(
  configuredUrl: string,
  locationLike: Pick<Location, 'protocol' | 'hostname'>,
  fetchImpl: typeof fetch,
): Promise<AuthoritySelection> {
  const configured = new URL(
    configuredUrl,
    `${locationLike.protocol}//${locationLike.hostname}`,
  );
  const mode = normalizeMode(configured.searchParams.get('authority'));
  const endpointThreshold = boundedProbability(
    configured.searchParams.get('endpoint_threshold'),
  );
  const primaryUrl = toStreamingSttWebSocketUrl(configured);
  if (mode === 'observational') {
    return {
      websocketUrl: primaryUrl,
      authorityEnabled: false,
      mode,
      endpointThreshold,
      fallbackUsed: false,
      reasons: ['observational_mode'],
    };
  }

  const language = configured.searchParams.get('language')?.trim() || 'en';
  const authorityUrl = new URL('/authorityz', configured);
  authorityUrl.protocol = authorityUrl.protocol === 'wss:'
    ? 'https:'
    : authorityUrl.protocol === 'ws:'
      ? 'http:'
      : authorityUrl.protocol;
  authorityUrl.search = '';
  authorityUrl.searchParams.set('language', language);
  authorityUrl.searchParams.set('mode', mode);

  let response: AuthorityResponse = {};
  let reasons: string[] = [];
  try {
    const authorityResponse = await fetchImpl(authorityUrl.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    response = await authorityResponse.json() as AuthorityResponse;
    if (!authorityResponse.ok) {
      reasons.push(`authority_http_${authorityResponse.status}`);
    }
  } catch (error) {
    reasons.push(
      error instanceof Error ? error.message : 'authority_probe_failed',
    );
  }
  reasons = [...reasons, ...(response.reasons ?? [])];
  if (response.eligible === true && response.ok !== false) {
    return {
      websocketUrl: primaryUrl,
      authorityEnabled: true,
      mode,
      endpointThreshold,
      fallbackUsed: false,
      reasons,
    };
  }

  const fallback = configured.searchParams.get('fallback')?.trim();
  if (!fallback) {
    throw new Error(
      `STT authority gate failed: ${reasons.join(', ') || 'not eligible'}`,
    );
  }
  return {
    websocketUrl: toStreamingSttWebSocketUrl(
      new URL(
        fallback,
        `${locationLike.protocol}//${locationLike.hostname}`,
      ),
    ),
    authorityEnabled: false,
    mode,
    endpointThreshold,
    fallbackUsed: true,
    reasons: reasons.length ? reasons : ['authority_not_eligible'],
  };
}

/**
 * Compatibility no-op for older bootstrap imports. Authority is resolved
 * before microphone capture and committed by the live voice controller.
 */
export function initializeLiveSttAuthorityController(): () => void {
  return () => undefined;
}

function toStreamingSttWebSocketUrl(input: URL): string {
  const url = new URL(input.toString());
  const language = url.searchParams.get('language')?.trim();
  url.protocol = url.protocol === 'https:' || url.protocol === 'wss:'
    ? 'wss:'
    : 'ws:';
  const normalizedPath = url.pathname.replace(/\/+$/, '');
  if (normalizedPath.endsWith('/ws/transcribe')) {
    url.pathname = normalizedPath;
  } else if (normalizedPath.endsWith('/transcribe')) {
    url.pathname = `${normalizedPath.slice(0, -'/transcribe'.length)}/ws/transcribe`;
  } else {
    url.pathname = `${normalizedPath}/ws/transcribe`.replace(/\/{2,}/g, '/');
  }
  url.search = '';
  if (language) url.searchParams.set('language', language);
  url.hash = '';
  return url.toString();
}

function normalizeMode(value: string | null): AuthorityMode {
  return value === 'test' || value === 'auto' ? value : 'observational';
}

function boundedProbability(value: string | null): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_ENDPOINT_THRESHOLD;
  return Math.max(0.5, Math.min(0.99, parsed));
}
