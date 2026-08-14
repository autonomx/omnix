import {
  isAssistantPcmStreamActive,
  startAssistantPcmStream,
  stopAssistantPcmStream,
} from './assistant-pcm-stream-websocket-player';

const STREAM_AUDIO_BUTTON_ATTRIBUTE = 'data-omnix-stream-audio';
const installedRoots = new WeakSet<ParentNode>();

export function initializeChatMessageStreamAudioController(root: ParentNode = document): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined' || installedRoots.has(root)) return () => undefined;
  installedRoots.add(root);

  injectStreamAudioButtons(root);
  const rootNode = root as Node;
  const eventTarget = root instanceof Document ? root : rootNode.ownerDocument ?? document;
  const observerTarget = root instanceof Document ? root.documentElement : rootNode;
  const observer = new MutationObserver(() => injectStreamAudioButtons(root));
  observer.observe(observerTarget, { childList: true, subtree: true });

  const handleClick = (event: Event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>(`button[${STREAM_AUDIO_BUTTON_ATTRIBUTE}]`);
    if (!button || !rootContains(root, button)) return;

    event.preventDefault();
    if (isAssistantPcmStreamActive(button)) {
      stopAssistantPcmStream(root, 'Streaming response audio stopped.');
      return;
    }

    const message = button.closest<HTMLElement>('.assistant-chat-message.assistant');
    const text = message?.querySelector<HTMLElement>('.assistant-chat-bubble > p')?.textContent?.trim() ?? '';
    if (!text) {
      setStreamAudioStatus(root, 'No assistant response is ready to stream.');
      return;
    }

    void startAssistantPcmStream(root, button, text);
  };

  eventTarget.addEventListener('click', handleClick, true);
  return () => {
    observer.disconnect();
    eventTarget.removeEventListener('click', handleClick, true);
    stopAssistantPcmStream(root);
    installedRoots.delete(root);
  };
}

export function injectStreamAudioButtons(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>('.assistant-chat-message.assistant .assistant-message-actions').forEach((actions) => {
    if (actions.querySelector(`[${STREAM_AUDIO_BUTTON_ATTRIBUTE}]`)) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '≋';
    button.title = 'Stream response audio';
    button.setAttribute('aria-label', 'Stream response audio');
    button.setAttribute(STREAM_AUDIO_BUTTON_ATTRIBUTE, 'true');

    const moreButton = actions.querySelector<HTMLButtonElement>('button[aria-label="More response actions"]');
    actions.insertBefore(button, moreButton ?? null);
  });
}

function setStreamAudioStatus(root: ParentNode, message: string): void {
  const host = root.querySelector<HTMLElement>('.assistant-inline-status');
  if (!host) return;
  let status = host.querySelector<HTMLElement>('[data-omnix-stream-audio-status]');
  if (!status) {
    status = document.createElement('span');
    status.setAttribute('data-omnix-stream-audio-status', 'true');
    status.setAttribute('role', 'status');
    host.appendChild(status);
  }
  status.textContent = message;
}

function rootContains(root: ParentNode, element: Element): boolean {
  return root instanceof Document ? root.documentElement.contains(element) : (root as Node).contains(element);
}
