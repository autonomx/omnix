import {
  StreamingSttWebSocketClient,
  calculateRms,
  getDefaultStreamingSttWebSocketUrl,
  type StreamingSttConnectionStatus,
  type StreamingSttWebSocketCtor,
} from './live-voice-websocket';
import { createAssistantWorkspaceRuntimeConfig } from './runtime-config';

type LiveVoiceWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
};

type LiveVoiceDomSession = {
  card: HTMLElement;
  stream: MediaStream;
  audioContext: AudioContext;
  audioPipeline: LiveVoiceAudioPipeline | null;
  source: MediaStreamAudioSourceNode;
  client: StreamingSttWebSocketClient;
  muted: boolean;
  speechDetected: boolean;
  finalRequested: boolean;
  silenceTimer: ReturnType<typeof setTimeout> | null;
  voiceLevel: number;
};

type LiveVoiceAudioPipeline = {
  node: AudioNode;
  cleanup: () => void;
};

type AssistantUtilityPanel = 'voice' | 'tools';

const enhancedCards = new WeakSet<HTMLElement>();
const enhancedUtilityGrids = new WeakSet<HTMLElement>();
const enhancedToolChips = new WeakSet<HTMLButtonElement>();
let activeSession: LiveVoiceDomSession | null = null;

const SPEECH_RMS_THRESHOLD = 0.015;
const SILENCE_FINALIZE_MS = 650;

export function initializeLiveVoiceWebSocketEnhancer(root: ParentNode = document): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  enhanceExistingCards(root);
  wireExistingToolChips(root);

  const observer = new MutationObserver(() => {
    enhanceExistingCards(root);
    wireExistingToolChips(root);
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function enhanceExistingCards(root: ParentNode): void {
  const cards = root.querySelectorAll<HTMLElement>('.assistant-live-card');

  cards.forEach((card) => {
    ensureUtilityPanelToggle(card);

    if (enhancedCards.has(card)) return;

    enhancedCards.add(card);
    wireLiveVoiceCard(card);
  });
}

function ensureUtilityPanelToggle(card: HTMLElement): void {
  const grid = card.closest<HTMLElement>('.assistant-live-tools-grid');
  if (!grid || enhancedUtilityGrids.has(grid)) return;

  const toggle = document.createElement('div');
  toggle.className = 'assistant-side-panel-toggle';
  toggle.setAttribute('role', 'tablist');
  toggle.setAttribute('aria-label', 'Assistant side panel');

  const voiceButton = createUtilityPanelToggleButton('Live Voice', 'voice');
  const toolsButton = createUtilityPanelToggleButton('Tools', 'tools');
  toggle.append(voiceButton, toolsButton);
  grid.before(toggle);

  enhancedUtilityGrids.add(grid);
  setActiveUtilityPanel(grid, 'voice');
}

function createUtilityPanelToggleButton(label: string, panel: AssistantUtilityPanel): HTMLButtonElement {
  const button = document.createElement('button');
  button.type = 'button';
  button.dataset.panel = panel;
  button.setAttribute('role', 'tab');
  button.textContent = label;
  button.addEventListener('click', () => {
    const grid = button.closest<HTMLElement>('.assistant-chat-side')?.querySelector<HTMLElement>('.assistant-live-tools-grid');
    if (grid) setActiveUtilityPanel(grid, panel);
  });
  return button;
}

function setActiveUtilityPanel(grid: HTMLElement, panel: AssistantUtilityPanel): void {
  grid.dataset.activePanel = panel;
  const toggle = grid.previousElementSibling instanceof HTMLElement && grid.previousElementSibling.classList.contains('assistant-side-panel-toggle')
    ? grid.previousElementSibling
    : null;

  toggle?.querySelectorAll<HTMLButtonElement>('button[data-panel]').forEach((button) => {
    const isActive = button.dataset.panel === panel;
    button.classList.toggle('active', isActive);
    button.setAttribute('aria-selected', String(isActive));
    button.tabIndex = isActive ? 0 : -1;
  });
}

function wireExistingToolChips(root: ParentNode): void {
  const chips = root.querySelectorAll<HTMLButtonElement>('.assistant-composer-chip');

  chips.forEach((chip) => {
    if (enhancedToolChips.has(chip) || !chip.textContent?.toLowerCase().includes('tools')) return;

    enhancedToolChips.add(chip);
    chip.addEventListener('click', () => {
      const grid = document.querySelector<HTMLElement>('.assistant-live-tools-grid');
      if (grid) setActiveUtilityPanel(grid, 'tools');
    });
  });
}

function wireLiveVoiceCard(card: HTMLElement): void {
  const stateButton = card.querySelector<HTMLElement>('.assistant-live-state');
  const buttons = Array.from(card.querySelectorAll<HTMLButtonElement>('button'));
  const muteButton = buttons.find((button) => button.textContent?.toLowerCase().includes('mute'));
  const callButton = buttons.find((button) => {
    const label = button.textContent?.toLowerCase() ?? '';
    return label.includes('start call') || label.includes('end call');
  });
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

  composerMicButton?.addEventListener('click', () => {
    const grid = card.closest<HTMLElement>('.assistant-live-tools-grid');
    if (grid) setActiveUtilityPanel(grid, 'voice');
    void startLiveVoice(card);
  });
  liveModeButton?.addEventListener('click', () => {
    const grid = card.closest<HTMLElement>('.assistant-live-tools-grid');
    if (grid) setActiveUtilityPanel(grid, 'voice');
  });
  muteButton?.addEventListener('click', () => toggleMute(card));
  callButton?.addEventListener('click', () => {
    if (activeSession?.card === card) {
      stopLiveVoice('idle');
      return;
    }

    void startLiveVoice(card);
  });
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
    const runtimeConfig = createAssistantWorkspaceRuntimeConfig();
    const client = new StreamingSttWebSocketClient({
      url: getDefaultStreamingSttWebSocketUrl(window.location, runtimeConfig.sttServiceUrl),
      webSocketCtor: WebSocketCtor,
      onStatusChange: (status) => setPanelStatus(card, status),
      onPartialTranscript: (text) => renderTranscript(card, 'You', text, 'draft'),
      onAcceptedFinal: async (final) => {
        handleFinalTranscript(card, final.text);
        return { outcome: 'conversation_submitted', segmentId: final.segmentId, sourceSequence: final.sourceSequence, taskContractId: 'legacy-enhancer', taskContractVersion: 1 };
      },
      onError: (message) => showLiveVoiceError(card, message),
    });

    const session: LiveVoiceDomSession = {
      card,
      stream,
      audioContext,
      audioPipeline: null,
      source,
      client,
      muted: false,
      speechDetected: false,
      finalRequested: false,
      silenceTimer: null,
      voiceLevel: 0,
    };

    activeSession = session;
    const audioPipeline = await createLiveVoiceAudioPipeline(audioContext, (audio) => processAudioFrame(session, audio));
    session.audioPipeline = audioPipeline;
    source.connect(audioPipeline.node);

    await client.connect();
    setPanelStatus(card, 'connected');
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Could not start live voice.';
    showLiveVoiceError(card, message);
    stopLiveVoice('error');
  }
}

async function createLiveVoiceAudioPipeline(audioContext: AudioContext, onAudioFrame: (audio: Float32Array) => void): Promise<LiveVoiceAudioPipeline> {
  if ('audioWorklet' in audioContext && typeof AudioWorkletNode !== 'undefined') {
    try {
      await ensureLiveVoiceWorklet(audioContext);
      const node = new AudioWorkletNode(audioContext, 'omnix-live-voice-processor');
      const silentOutput = audioContext.createGain();
      silentOutput.gain.value = 0;
      node.port.onmessage = (event: MessageEvent<Float32Array>) => onAudioFrame(new Float32Array(event.data));
      node.connect(silentOutput);
      silentOutput.connect(audioContext.destination);
      return {
        node,
        cleanup: () => {
          node.port.onmessage = null;
          node.disconnect();
          silentOutput.disconnect();
        },
      };
    } catch {
      // Keep the older path available for browsers that reject dynamic worklet modules.
    }
  }

  const processor = audioContext.createScriptProcessor(1024, 1, 1);
  processor.onaudioprocess = (event) => onAudioFrame(new Float32Array(event.inputBuffer.getChannelData(0)));
  processor.connect(audioContext.destination);
  return {
    node: processor,
    cleanup: () => {
      processor.onaudioprocess = null;
      processor.disconnect();
    },
  };
}

let liveVoiceWorkletModuleUrl: string | null = null;
const liveVoiceWorkletContexts = new WeakSet<AudioContext>();

async function ensureLiveVoiceWorklet(audioContext: AudioContext): Promise<void> {
  if (liveVoiceWorkletContexts.has(audioContext)) return;

  liveVoiceWorkletModuleUrl ??= URL.createObjectURL(new Blob([`
class OmnixLiveVoiceProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      const audio = new Float32Array(channel);
      this.port.postMessage(audio, [audio.buffer]);
    }
    return true;
  }
}
registerProcessor('omnix-live-voice-processor', OmnixLiveVoiceProcessor);
`], { type: 'text/javascript' }));

  await audioContext.audioWorklet.addModule(liveVoiceWorkletModuleUrl);
  liveVoiceWorkletContexts.add(audioContext);
}

function processAudioFrame(session: LiveVoiceDomSession, audio: Float32Array): void {
  if (session.finalRequested || session.muted) return;

  const rms = calculateRms(audio);
  updateVoiceVisualizer(session, rms);

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

function updateVoiceVisualizer(session: LiveVoiceDomSession, rms: number): void {
  const rawLevel = clamp(rms / 0.12, 0, 1);
  session.voiceLevel = session.voiceLevel * 0.72 + rawLevel * 0.28;
  const barScale = 0.22 + session.voiceLevel * 0.9;
  const ambientScale = 0.92 + session.voiceLevel * 0.24;
  const coreScale = 1 + session.voiceLevel * 0.08;
  const inputScale = Math.max(0.08, session.voiceLevel);
  session.card.style.setProperty('--voice-level', session.voiceLevel.toFixed(3));
  session.card.style.setProperty('--voice-bar-scale', barScale.toFixed(3));
  session.card.style.setProperty('--voice-ambient-scale', ambientScale.toFixed(3));
  session.card.style.setProperty('--voice-core-scale', coreScale.toFixed(3));
  session.card.style.setProperty('--voice-input-scale', inputScale.toFixed(3));
  session.card.dataset.voiceInput = session.voiceLevel >= 0.14 ? 'active' : 'listening';
  const inputStatus = session.card.querySelector<HTMLElement>('.assistant-voice-input-status');
  if (inputStatus) inputStatus.textContent = session.voiceLevel >= 0.14 ? 'Hearing you' : 'Listening';
  const orb = session.card.querySelector<HTMLElement>('.assistant-voice-orb');
  orb?.setAttribute('data-voice-mode', session.muted ? 'idle' : 'listening');
}

function resetVoiceVisualizer(card: HTMLElement): void {
  card.style.removeProperty('--voice-level');
  card.style.removeProperty('--voice-bar-scale');
  card.style.removeProperty('--voice-ambient-scale');
  card.style.removeProperty('--voice-core-scale');
  card.style.removeProperty('--voice-input-scale');
  card.dataset.voiceInput = 'idle';
  const inputStatus = card.querySelector<HTMLElement>('.assistant-voice-input-status');
  if (inputStatus) inputStatus.textContent = 'Idle';
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
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

  session.audioPipeline?.cleanup();
  session.source.disconnect();
  session.audioContext.close().catch(() => {});
  session.stream.getTracks().forEach((track) => track.stop());
  session.client.disconnect();
  setPanelStatus(session.card, nextStatus);
  resetVoiceVisualizer(session.card);
  activeSession = null;
}

function setPanelStatus(card: HTMLElement, status: StreamingSttConnectionStatus): void {
  const connectedLabel = card.querySelector('header strong');
  const state = card.querySelector('.assistant-live-state span:first-child');
  const statusLabel = card.querySelector('.assistant-voice-status strong');
  const callButton = Array.from(card.querySelectorAll<HTMLButtonElement>('button')).find((button) => {
    const label = button.textContent?.toLowerCase() ?? '';
    return label.includes('start call') || label.includes('end call');
  });
  const isCallActive = status === 'connected' || status === 'connecting';

  const stateText = status === 'connected' ? 'Listening' : status === 'connecting' ? 'Connecting' : status === 'error' ? 'Error' : 'Idle';
  if (state) state.textContent = stateText;
  if (statusLabel) statusLabel.textContent = stateText;
  if (connectedLabel) connectedLabel.textContent = status === 'connected' ? 'Connected' : status === 'connecting' ? 'Connecting' : 'Disconnected';
  if (callButton) {
    callButton.textContent = isCallActive ? 'End Call' : 'Start Call';
    callButton.classList.toggle('danger', isCallActive);
    callButton.setAttribute('aria-label', isCallActive ? 'End live voice call' : 'Start live voice call');
    callButton.disabled = status === 'connecting';
  }
  card.dataset.liveVoiceStatus = status;
  card.dataset.voiceInput = status === 'connected' ? 'listening' : status === 'connecting' ? 'connecting' : status === 'error' ? 'error' : 'idle';
  const inputStatus = card.querySelector<HTMLElement>('.assistant-voice-input-status');
  if (inputStatus) {
    inputStatus.textContent = status === 'connected' ? 'Listening' : status === 'connecting' ? 'Connecting' : status === 'error' ? 'Input error' : 'Idle';
  }
  const orb = card.querySelector<HTMLElement>('.assistant-voice-orb');
  if (orb) {
    orb.setAttribute('data-voice-mode', status === 'connected' ? 'listening' : status === 'error' ? 'error' : 'idle');
  }
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
