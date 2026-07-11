import {
  readEffectiveLiveConversationProfile,
  type LiveConversationProfile,
} from '../chatbot/liveConversationProfileClient';
import { readActivePronunciations } from '../chatbot/livePronunciationClient';
import {
  applyDeliveryPlanToTtsRequest,
  createSpeechDeliveryPlan,
  type SpeechDeliveryPlan,
} from './live-speech-delivery-plan';

const LIVE_TTS_PATH = '/api/tts/live-call/websocket';
const PLAN_EVENT = 'omnix:live-speech-delivery-plan';
const INSTALL_FLAG = '__omnixLiveSpeechDeliveryBridgeInstalled';

type DeliveryWindow = Window & typeof globalThis & {
  __omnixLiveSpeechDeliveryBridgeInstalled?: boolean;
  WebSocket: typeof WebSocket;
};

export function initializeLiveSpeechDeliveryBridge(): () => void {
  if (typeof window === 'undefined' || !window.WebSocket) return () => undefined;
  const liveWindow = window as DeliveryWindow;
  if (liveWindow.__omnixLiveSpeechDeliveryBridgeInstalled) return () => undefined;
  const OriginalWebSocket = liveWindow.WebSocket;
  liveWindow.__omnixLiveSpeechDeliveryBridgeInstalled = true;

  const WrappedWebSocket = new Proxy(OriginalWebSocket, {
    construct(target, args, newTarget) {
      const socket = Reflect.construct(target, args, newTarget) as WebSocket;
      const url = String(args[0] ?? '');
      if (new URL(url, window.location.origin).pathname === LIVE_TTS_PATH) wrapLiveSocket(socket);
      return socket;
    },
  });
  liveWindow.WebSocket = WrappedWebSocket as typeof WebSocket;

  return () => {
    if (liveWindow.WebSocket === WrappedWebSocket) liveWindow.WebSocket = OriginalWebSocket;
    liveWindow.__omnixLiveSpeechDeliveryBridgeInstalled = false;
  };
}

export function enrichLiveTtsFrame(
  frame: Record<string, unknown>,
  profile: LiveConversationProfile | null,
): { frame: Record<string, unknown>; plan: SpeechDeliveryPlan | null } {
  if (frame.type !== 'synthesize' || typeof frame.text !== 'string' || !profile) return { frame, plan: null };
  const text = frame.text.trim();
  const serious = /\b(?:sorry|grief|loss|afraid|hurt|serious|take your time)\b/i.test(text);
  const plan = createSpeechDeliveryPlan(text, profile, serious);
  return {
    frame: {
      ...applyDeliveryPlanToTtsRequest(frame, plan),
      pronunciation_lexicon: readActivePronunciations().map((entry) => ({
        phrase: entry.phrase,
        pronunciation: entry.pronunciation,
        locale: entry.locale,
      })),
    },
    plan,
  };
}

function wrapLiveSocket(socket: WebSocket): void {
  const originalSend = socket.send.bind(socket);
  socket.send = ((data: string | ArrayBufferLike | Blob | ArrayBufferView) => {
    if (typeof data !== 'string') return originalSend(data);
    try {
      const payload = JSON.parse(data) as Record<string, unknown>;
      const enriched = enrichLiveTtsFrame(payload, readEffectiveLiveConversationProfile());
      if (enriched.plan) window.dispatchEvent(new CustomEvent(PLAN_EVENT, { detail: enriched.plan }));
      return originalSend(JSON.stringify(enriched.frame));
    } catch {
      return originalSend(data);
    }
  }) as typeof socket.send;
}
