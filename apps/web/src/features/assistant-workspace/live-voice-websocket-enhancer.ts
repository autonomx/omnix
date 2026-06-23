import {
  StreamingSttWebSocketClient,
  calculateRms,
  getDefaultStreamingSttWebSocketUrl,
  type StreamingSttConnectionStatus,
  type StreamingSttWebSocketCtor,
} from './live-voice-websocket';

type LiveVoiceWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
};

type LiveVoiceDomSession = {
  card: HTMLElement;
  stream: MediaStream;
  audioContext: AudioContext;
  processor: ScriptProcessorNode;
  source: MediaStreamAudioSourceNode;
  client: StreamingSttWebSocketClient;
  muted: boolean;
  speechDetected: boolean;
  finalRequested: boolean;
  silenceTimer: ReturnType<typeof setTimeout> | null;
};

const enhancedCards = new WeakSet<HTMLElement>();
let activeSession: LiveVoiceDomSession | null = null;

const SPEECH_RMS_THRESHOLD = 0.015;
const SILENCE_FINALIZE_MS = 650;

export function initializeLiveVoiceWebSocketEnhancer(root: ParentNode = document): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  enhanceExistingCards(root);

  const observer = new MutationObserver(() => enhanceExistingCards(root));
  observer.observe(document.body, { childList: true, subtree: true });
}

function enhanceExistingCards(root: ParentNode): void {
  const cards = root.querySelectorAll<HTMLElement>('.assistant-live-card');

  cards.forEach((card) => {
    if (enhancedCards.has(card)) return;

    enhancedCards.add(card);
    wireLiveVoiceCard(card);
  });
}

function wireLiveVoiceCard(card: HTMLElement): void {
  const stateButton = card.querySelector<HTMLElement>('.assistant-live-state');
  const buttons = Array.from(card.querySelectorAll<HTMLButtonElement>('button'));
  const muteButton = buttons.find((button) => button.textContent?.toLowerCase().includes('mute'));
  const endButton = buttons.find((button) => button.textContent?.toLowerCase().includes('end call'));
  const clearButton = buttons.find((button) => button.textContent?.toLowerCase().includes('clear'));
  const composerMicButton = document.querySelector<HTMLButtonElement>('.assistant-mic-button');
  const liveModeButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.assistant-mode-switch button'))
    .find((button) => button.textContent?.toLowerCase().includes('live voice'));

  stateButton?.setAttribute('role', 'button');
  stateButton?.setAttribute('tabIndex', '0');
  stateButton?.setAttribute('aria-label', 'Start live voice streaming');
  stateButton?.addEventListener('click', () => void startLiveVoice(card));
  stateButton?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      void startLiveVoice(card);
    }
  });

  composerMicButton?.addEventListener('click', () => void startLiveVoice(card));
  liveModeButton?.addEventListener('click', () => void startLiveVoice(card));
  muteButton?.addEventListener('click', () => toggleMute(card));
  endButton?.addEventListener('click', () => stopLiveVoice('idle'));
  clearButton?.addEventListener('click', () => clearTranscript(card));

  setPanelStatus(card, 'idle');
}

async function startLiveVoice(card: HTMLElement): Promise<void> {
  if (activeSession) {
    if (activeSession.card === card) return;
    stopLiveVoice('idle');
  }

  try {
    setPanelStatus(card, 'connecting');

    const liveWindow = window as LiveVoiceWindow;
    const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
    const WebSocketCtor = liveWindow.WebSocket as unknown as StreamingSttWebSocketCtor | undefined;

    if (!AudioContextCtor || !WebSocketCtor) {
      throw new Error('Live voice requires browser AudioContext and WebSocket support.');
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Live voice requires browser microphone access.');
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    const audioContext = new AudioContextCtor({ latencyHint: 'interactive' });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(1024, 1, 1);
    const client = new StreamingSttWebSocketClient({
      url: getDefaultStreamingSttWebSocketUrl(window.location),
      webSocketCtor: WebSocketCtor,
      onStatusChange: (status) => setPanelStatus(card, status),
      onPartialTranscript: (text) => renderTranscript(card, 'You', text, 'draft'),
      onFinalTranscript: (text) => handleFinalTranscript(card, text),
      onError: (message) => showLiveVoiceError(card, message),
    });

    const session: LiveVoiceDomSession = {
      card,
      stream,
      audioContext,
      processor,
      source,
      client,
      muted: false,
      speechDetected: false,
      finalRequested: false,
      silenceTimer: null,
    };

    activeSession = session;
    processor.onaudioprocess = (event) => processAudioFrame(session, event);
    source.connect(processor);
    processor.connect(audioContext.destination);

    await client.connect();
    setPanelStatus(card, 'connected');
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Could not start live voice.';
    showLiveVoiceError(card, message);
    stopLiveVoice('error');
  }
}

function processAudioFrame(session: LiveVoiceDomSession, event: AudioProcessingEvent): void {
  if (session.finalRequested || session.muted) return;

  const audio = new Float32Array(event.inputBuffer.getChannelData(0));
  const rms = calculateRms(audio);

  if (rms >= SPEECH_RMS_THRESHOLD) {
    session.speechDetected = true;
    if (session.silenceTimer) {
      clearTimeout(session.silenceTimer);
      session.silenceTimer = null;
    }
  } else if (session.speechDetected && !session.silenceTimer) {
    session.silenceTimer = setTimeout(() => {
      session.finalRequested = true;
      session.client.sendFinal();
    }, SILENCE_FINALIZE_MS);
  }

  session.client.sendAudio(audio, session.audioContext.sampleRate);
}

function handleFinalTranscript(card: HTMLElement, text: string): void {
  const transcript = text.trim();
  if (!transcript) {
    setPanelStatus(card, 'connected');
    return;
  }

  renderTranscript(card, 'You', transcript, 'final');
  populateComposer(transcript);
  submitComposer();
  stopLiveVoice('idle');
}

function toggleMute(card: HTMLElement): void {
  if (!activeSession || activeSession.card !== card) return;

  activeSession.muted = !activeSession.muted;
  const muteButton = Array.from(card.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => button.textContent?.toLowerCase().includes('mute') || button.textContent?.toLowerCase().includes('unmute'));

  if (muteButton) {
    muteButton.textContent = activeSession.muted ? 'Unmute' : 'Mute';
    muteButton.setAttribute('aria-pressed', String(activeSession.muted));
  }

  setPanelStatus(card, activeSession.muted ? 'disconnected' : 'connected');
}

function stopLiveVoice(nextStatus: StreamingSttConnectionStatus = 'idle'): void {
  const session = activeSession;
  if (!session) return;

  if (session.silenceTimer) {
    clearTimeout(session.silenceTimer);
  }

  session.processor.disconnect();
  session.source.disconnect();
  session.audioContext.close().catch(() => {});
  session.stream.getTracks().forEach((track) => track.stop());
  session.client.disconnect();
  setPanelStatus(session.card, nextStatus);
  activeSession = null;
}

function setPanelStatus(card: HTMLElement, status: StreamingSttConnectionStatus): void {
  const connectedLabel = card.querySelector('header strong');
  const state = card.querySelector('.assistant-live-state span:first-child');
  const statusLabel = card.querySelector('.assistant-voice-status strong');

  const stateText = status === 'connected' ? 'Listening' : status === 'connecting' ? 'Connecting' : status === 'error' ? 'Error' : 'Idle';
  if (state) state.textContent = stateText;
  if (statusLabel) statusLabel.textContent = stateText;
  if (connectedLabel) connectedLabel.textContent = status === 'connected' ? 'Connected' : status === 'connecting' ? 'Connecting' : 'Disconnected';
  card.dataset.liveVoiceStatus = status;
}

function renderTranscript(card: HTMLElement, speaker: 'You' | 'Omnix', text: string, mode: 'draft' | 'final'): void {
  const container = card.querySelector<HTMLElement>('.assistant-voice-transcript');
  if (!container) return;

  const className = speaker === 'Omnix' ? 'assistant' : 'user';
  const rowId = mode === 'draft' ? 'live-voice-draft' : `live-voice-${Date.now()}`;
  let row = container.querySelector<HTMLParagraphElement>(`p[data-live-voice-id="${rowId}"]`);

  if (!row) {
    row = document.createElement('p');
    row.className = className;
    row.dataset.liveVoiceId = rowId;
    const header = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = speaker;
    const time = document.createElement('time');
    const now = new Date();
    time.dateTime = now.toISOString();
    time.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    header.append(name, time);
    row.append(header, document.createTextNode(text));
    container.append(row);
  } else {
    const textNode = Array.from(row.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
    if (textNode) {
      textNode.textContent = text;
    } else {
      row.append(document.createTextNode(text));
    }
  }

  if (mode === 'final') {
    row.dataset.liveVoiceId = `live-voice-${Date.now()}`;
  }
}

function showLiveVoiceError(card: HTMLElement, message: string): void {
  renderTranscript(card, 'Omnix', message, 'final');
  setPanelStatus(card, 'error');
}

function clearTranscript(card: HTMLElement): void {
  const rows = card.querySelectorAll('.assistant-voice-transcript p');
  rows.forEach((row) => row.remove());
}

function populateComposer(text: string): void {
  const textarea = document.querySelector<HTMLTextAreaElement>('.assistant-message-input textarea');
  if (!textarea) return;

  textarea.value = text;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

function submitComposer(): void {
  const form = document.querySelector<HTMLFormElement>('.assistant-composer');
  if (!form) return;

  if (typeof form.requestSubmit === 'function') {
    form.requestSubmit();
  } else {
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  }
}

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initializeLiveVoiceWebSocketEnhancer(), { once: true });
  } else {
    initializeLiveVoiceWebSocketEnhancer();
  }
}
