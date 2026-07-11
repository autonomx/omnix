import {
  playBufferedTts,
  stopBufferedTtsPlayback,
  type BufferedTtsPlaybackState,
} from './assistant-buffered-tts-player';
import { stopAssistantPcmStream } from './assistant-pcm-stream-websocket-player';

const STREAM_AUDIO_BUTTON_ATTRIBUTE = 'data-omnix-stream-audio';
const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const AUDIO_PLAYBACK_STATE_EVENT = 'omnix:assistant-audio-playback-state';
const INSTALLED_KEY = '__omnixChatMessageAudioControllerV2Installed';

let activeButton: HTMLButtonElement | null = null;

export function initializeChatMessageAudioControllerV2(root: ParentNode = document): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const state = window as typeof window & Record<string, unknown>;
  if (state[INSTALLED_KEY]) return () => undefined;
  state[INSTALLED_KEY] = true;

  const handleClick = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>('button');
    if (!button || !rootContains(root, button) || !isChatAudioButton(button)) return;

    if (isStreamAudioButton(button)) {
      const stopping = button.getAttribute('aria-pressed') === 'true';
      stopActiveButton(root);
      dispatchLiveAudioPreemption('manual-stream-button');
      if (stopping) announceAudioPlayback(false, 'manual-stream');
      // Preserve the existing low-latency stream-button handler. This capture listener
      // only clears competing pipelines before that handler runs.
      return;
    }

    const message = button.closest<HTMLElement>('.assistant-chat-message.assistant');
    const text = message?.querySelector<HTMLElement>('.assistant-chat-bubble > p')?.textContent?.trim() ?? '';
    if (!text) {
      setStatus(root, 'No assistant response is ready to play.');
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    if (activeButton === button && button.getAttribute('aria-pressed') === 'true') {
      stopActiveButton(root, 'Response audio stopped.');
      return;
    }

    dispatchLiveAudioPreemption('manual-play-button');
    stopAssistantPcmStream(root);
    stopActiveButton(root);
    activeButton = button;
    setButtonState(button, true);
    void playBufferedTts(text, {
      voiceId: selectedVoiceId(),
      onStateChange: (playbackState) => handlePlaybackState(root, button, playbackState),
    }).catch((error: unknown) => {
      if (activeButton !== button) return;
      setButtonState(button, false);
      activeButton = null;
      announceAudioPlayback(false, 'manual-play');
      if (error instanceof DOMException && error.name === 'AbortError') {
        setStatus(root, 'Response audio stopped.');
        return;
      }
      setStatus(root, error instanceof Error ? error.message : 'Response audio playback failed.');
    });
  };

  const eventTarget = root instanceof Document ? root : (root as Node).ownerDocument ?? document;
  eventTarget.addEventListener('click', handleClick, true);
  return () => {
    eventTarget.removeEventListener('click', handleClick, true);
    stopActiveButton(root);
    delete state[INSTALLED_KEY];
  };
}

export function isChatAudioButton(button: HTMLButtonElement): boolean {
  if (isStreamAudioButton(button)) return true;
  if (button.getAttribute('aria-label')?.trim().toLowerCase() === 'play response audio') return true;
  return button.textContent?.trim().toLowerCase() === 'play audio'
    && Boolean(button.closest('.assistant-chat-message.assistant'));
}

export function isStreamAudioButton(button: HTMLButtonElement): boolean {
  return button.hasAttribute(STREAM_AUDIO_BUTTON_ATTRIBUTE);
}

function handlePlaybackState(
  root: ParentNode,
  button: HTMLButtonElement,
  playbackState: BufferedTtsPlaybackState,
): void {
  if (activeButton !== button) return;
  if (playbackState === 'buffering') {
    announceAudioPlayback(false, 'manual-play');
    setStatus(root, 'Generating and buffering response audio…');
    return;
  }
  if (playbackState === 'playing') {
    announceAudioPlayback(true, 'manual-play');
    setStatus(root, 'Playing response audio.');
    return;
  }
  if (playbackState === 'finished' || playbackState === 'stopped') {
    setButtonState(button, false);
    activeButton = null;
    announceAudioPlayback(false, 'manual-play');
    setStatus(root, playbackState === 'finished' ? 'Response audio finished.' : 'Response audio stopped.');
  }
}

function stopActiveButton(root: ParentNode, status?: string): void {
  stopBufferedTtsPlayback();
  if (activeButton) setButtonState(activeButton, false);
  activeButton = null;
  announceAudioPlayback(false, 'manual-play');
  if (status) setStatus(root, status);
}

function setButtonState(button: HTMLButtonElement, active: boolean): void {
  button.setAttribute('aria-pressed', active ? 'true' : 'false');
  button.dataset.audioPlayback = active ? 'active' : 'idle';
}

function dispatchLiveAudioPreemption(source: string): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_INTERRUPT_EVENT, {
    detail: { source, intent: 'audio-preempt', confidence: 1 },
  }));
}

function announceAudioPlayback(speaking: boolean, source: string): void {
  window.dispatchEvent(new CustomEvent(AUDIO_PLAYBACK_STATE_EVENT, {
    detail: { speaking, source },
  }));
}

function selectedVoiceId(): string | null {
  const liveCallVoice = document.querySelector<HTMLElement>('.assistant-live-card')?.dataset.liveVoiceId?.trim();
  if (liveCallVoice) return liveCallVoice;
  const selected = document.querySelector<HTMLSelectElement>('select[aria-label="Cloned voice"]')?.value.trim();
  if (selected) return selected;
  try {
    const parsed = JSON.parse(window.localStorage.getItem('omnix.chatbot.assistantSettings') || '{}') as { voiceId?: unknown };
    return typeof parsed.voiceId === 'string' && parsed.voiceId.trim() ? parsed.voiceId.trim() : null;
  } catch {
    return null;
  }
}

function setStatus(root: ParentNode, message: string): void {
  const host = root.querySelector<HTMLElement>('.assistant-inline-status');
  if (!host) return;
  let status = host.querySelector<HTMLElement>('[data-omnix-chat-audio-status]');
  if (!status) {
    status = document.createElement('span');
    status.setAttribute('data-omnix-chat-audio-status', 'true');
    status.setAttribute('role', 'status');
    host.append(status);
  }
  status.textContent = message;
}

function rootContains(root: ParentNode, element: Element): boolean {
  return root instanceof Document ? root.documentElement.contains(element) : (root as Node).contains(element);
}
