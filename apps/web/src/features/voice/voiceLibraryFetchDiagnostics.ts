type AssetRecordLike = {
  id?: unknown;
  module?: unknown;
  storage_path?: unknown;
  type?: unknown;
  metadata?: unknown;
};

let installed = false;
let previousFetch: typeof window.fetch | null = null;

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  if (typeof Request !== 'undefined' && input instanceof Request) return input.method.toUpperCase();
  return 'GET';
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function isAssetListRequest(rawUrl: string): boolean {
  try {
    const base = typeof window !== 'undefined' ? window.location.href : 'http://localhost/';
    return new URL(rawUrl, base).pathname === '/api/assets';
  } catch {
    return rawUrl.split('?', 1)[0].endsWith('/api/assets');
  }
}

function elapsedMs(startedAt: number): number {
  const now = typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now();
  return Math.max(0, Math.round((now - startedAt) * 10) / 10);
}

function startedAt(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now();
}

function voiceProfileSummary(body: string): Record<string, unknown> {
  if (!body.trim()) return { responseBody: '' };
  try {
    const parsed = JSON.parse(body) as { assets?: unknown };
    const assets = Array.isArray(parsed.assets) ? parsed.assets as AssetRecordLike[] : [];
    const voiceProfiles = assets.filter((asset) => asset.type === 'voice_profile' || asset.module === 'voice-cloning');
    return {
      assetCount: assets.length,
      voiceProfileCount: voiceProfiles.length,
      voiceProfiles: voiceProfiles.slice(0, 50).map((asset) => {
        const metadata = asset.metadata && typeof asset.metadata === 'object'
          ? asset.metadata as Record<string, unknown>
          : {};
        return {
          id: asset.id,
          name: metadata.profile_name ?? metadata.voice_id ?? metadata.speaker,
          storagePath: asset.storage_path,
        };
      }),
    };
  } catch {
    return { responseBody: body.slice(0, 2_000) };
  }
}

function errorSummary(error: unknown): Record<string, unknown> {
  if (error instanceof Error) {
    return { name: error.name, message: error.message, stack: error.stack };
  }
  return { error };
}

export function installVoiceLibraryFetchDiagnostics(fetchImpl?: typeof fetch): void {
  if (installed || typeof window === 'undefined') return;

  previousFetch = window.fetch;
  const delegate = fetchImpl ?? window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const rawUrl = requestUrl(input);
    if (!isAssetListRequest(rawUrl)) return delegate(input, init);

    const method = requestMethod(input, init);
    const started = startedAt();
    const resolvedUrl = (() => {
      try {
        return new URL(rawUrl, window.location.href).toString();
      } catch {
        return rawUrl;
      }
    })();

    console.info('[Voice Library][HTTP] request started', {
      method,
      requestUrl: resolvedUrl,
      pageUrl: window.location.href,
    });

    try {
      const response = await delegate(input, init);
      let body = '';
      try {
        body = await response.clone().text();
      } catch (error) {
        console.warn('[Voice Library][HTTP] response body could not be inspected', errorSummary(error));
      }

      const detail = {
        method,
        requestUrl: resolvedUrl,
        pageUrl: window.location.href,
        status: response.status,
        statusText: response.statusText,
        ok: response.ok,
        contentType: response.headers.get('content-type'),
        elapsedMs: elapsedMs(started),
        ...voiceProfileSummary(body),
      };
      if (response.ok) {
        console.info('[Voice Library][HTTP] request completed', detail);
      } else {
        console.error('[Voice Library][HTTP] request failed', detail);
      }
      return response;
    } catch (error) {
      console.error('[Voice Library][HTTP] network request threw', {
        method,
        requestUrl: resolvedUrl,
        pageUrl: window.location.href,
        elapsedMs: elapsedMs(started),
        ...errorSummary(error),
      });
      throw error;
    }
  };
  installed = true;
}

export function resetVoiceLibraryFetchDiagnosticsForTests(): void {
  if (typeof window !== 'undefined' && previousFetch) window.fetch = previousFetch;
  previousFetch = null;
  installed = false;
}
