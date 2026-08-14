import {
  planConversationRepair,
  type LiveConversationRepairContext,
} from './live-conversation-repair';

const PERF_EVENT = 'omnix:assistant-voice-perf';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const REPAIR_EVENT = 'omnix:live-conversation-repair-planned';
const INSTALL_FLAG = '__omnixLiveConversationRepairInstalled';
const CONTEXT_MESSAGE_PATH = /\/api\/assistant\/context\/chat\/sessions\/[^/]+\/messages(?:\/stream)?$/;

type RepairWindow = Window & typeof globalThis & {
  __omnixLiveConversationRepairInstalled?: boolean;
};

type OverlapPerfDetail = {
  stage?: unknown;
  intent?: unknown;
  reason?: unknown;
  confidence?: unknown;
  transcript?: unknown;
};

let pendingRepair: LiveConversationRepairContext | null = null;

export function initializeLiveConversationRepairController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const liveWindow = window as RepairWindow;
  if (liveWindow.__omnixLiveConversationRepairInstalled) return () => undefined;
  liveWindow.__omnixLiveConversationRepairInstalled = true;

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const injection = injectRepairIntoRequest(input, init, pendingRepair);
    if (injection.consumed) pendingRepair = null;
    return originalFetch(injection.input, injection.init);
  };

  const handlePerf = (event: Event) => {
    const detail = (event as CustomEvent<OverlapPerfDetail>).detail;
    if (detail?.stage !== 'overlap_classified') return;
    const intent = typeof detail.intent === 'string' ? detail.intent : null;
    if (intent === 'backchannel' || intent === 'noise' || intent === 'uncertain') return;
    const transcript = typeof detail.transcript === 'string' && detail.transcript.trim()
      ? detail.transcript.trim()
      : currentLiveTranscript();
    const repair = planConversationRepair({
      transcript,
      overlapIntent: intent,
      overlapReason: typeof detail.reason === 'string' ? detail.reason : null,
      confidence: typeof detail.confidence === 'number' ? detail.confidence : null,
      assistantWasInterrupted: true,
    });
    if (!repair) return;
    pendingRepair = repair;
    window.dispatchEvent(new CustomEvent(REPAIR_EVENT, { detail: repair }));
  };
  const clear = () => { pendingRepair = null; };

  window.addEventListener(PERF_EVENT, handlePerf);
  window.addEventListener(STOP_EVENT, clear);

  return () => {
    window.removeEventListener(PERF_EVENT, handlePerf);
    window.removeEventListener(STOP_EVENT, clear);
    if (window.fetch !== originalFetch) window.fetch = originalFetch;
    pendingRepair = null;
    liveWindow.__omnixLiveConversationRepairInstalled = false;
  };
}

export function injectRepairIntoRequest(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  repair: LiveConversationRepairContext | null,
): { input: RequestInfo | URL; init?: RequestInit; consumed: boolean } {
  if (!repair || !init?.body || typeof init.body !== 'string') return { input, init, consumed: false };
  const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const pathname = new URL(raw, window.location.origin).pathname;
  if (!CONTEXT_MESSAGE_PATH.test(pathname) || (init.method ?? 'GET').toUpperCase() !== 'POST') {
    return { input, init, consumed: false };
  }
  try {
    const payload = JSON.parse(init.body) as Record<string, unknown>;
    if (typeof payload.content !== 'string' || !payload.content.trim()) return { input, init, consumed: false };
    return {
      input,
      init: { ...init, body: JSON.stringify({ ...payload, live_repair: repair }) },
      consumed: true,
    };
  } catch {
    return { input, init, consumed: false };
  }
}

export function currentLiveTranscript(root: ParentNode = document): string {
  const draft = root.querySelector<HTMLElement>('.assistant-live-draft p')?.textContent?.trim();
  if (draft && !draft.startsWith('Start Live Voice')) return draft;
  const row = root.querySelector<HTMLElement>('.assistant-voice-transcript [data-live-voice-id="live-voice-draft"]');
  if (!row) return '';
  const clone = row.cloneNode(true) as HTMLElement;
  clone.querySelector('span')?.remove();
  return clone.textContent?.trim() ?? '';
}
