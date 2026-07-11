export type LegacyLiveCallSnapshot = {
  connected: boolean;
  state: string;
  identity: string;
  duplexMode: string;
};

export type LiveChatMirroredMessage = {
  id: string;
  role: 'assistant' | 'user' | 'system';
  label: string;
  text: string;
  timestamp: string | null;
};

export type LiveChatMirroredAvatar = {
  imageUrl: string | null;
  alt: string;
  backgroundImage: string;
  mouthFrame: string;
  voiceMode: string;
};

const DEFAULT_LEGACY_SNAPSHOT: LegacyLiveCallSnapshot = {
  connected: false,
  state: 'Idle',
  identity: 'System Assistant',
  duplexMode: 'Safe half-duplex',
};

/** Compatibility-only DOM read for the legacy call button tests. Runtime policy uses the store. */
export function readLiveCallSnapshot(root: ParentNode = document): LegacyLiveCallSnapshot {
  const card = root.querySelector<HTMLElement>('.assistant-live-card');
  if (!card) return DEFAULT_LEGACY_SNAPSHOT;
  const action = Array.from(card.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => /^(?:Start Call|End Call)$/i.test(button.textContent?.trim() ?? ''));
  const state = card.querySelector<HTMLElement>('.assistant-live-state span')?.textContent?.trim()
    || card.querySelector<HTMLElement>('.assistant-voice-status strong')?.textContent?.trim()
    || 'Idle';
  const identity = card.querySelector<HTMLElement>('.assistant-live-identity')?.textContent?.trim()
    || 'System Assistant';
  const duplexMode = card.dataset.duplexMode === 'echo_aware'
    ? 'Echo-aware barge-in'
    : card.dataset.duplexGate === 'assistant-speaking'
      ? 'Safe half-duplex · microphone paused during playback'
      : 'Safe half-duplex';
  return {
    connected: action?.textContent?.trim().toLocaleLowerCase() === 'end call',
    state,
    identity,
    duplexMode,
  };
}

export function invokeExistingLiveCallControl(root: ParentNode = document): boolean {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('.assistant-live-card button'))
    .find((candidate) => /^(?:Start Call|End Call)$/i.test(candidate.textContent?.trim() ?? ''));
  if (!button) return false;
  button.click();
  return true;
}

export function liveCallCharacterName(identity: string): string {
  return identity.replace(/^Talking to\s+/i, '').trim() || 'Assistant';
}

/**
 * Mirrors the existing transcript owner for immersive presentation only.
 * No messages are persisted and no chat/session request is issued here.
 */
export function readLiveChatMirroredMessages(root: ParentNode = document): LiveChatMirroredMessage[] {
  const chatMessages = Array.from(root.querySelectorAll<HTMLElement>('.assistant-chat-messages .assistant-chat-message'));
  const source = chatMessages.length
    ? chatMessages
    : Array.from(root.querySelectorAll<HTMLElement>('.assistant-voice-transcript > p:not(.muted)'));

  return source.map((node, index) => {
    const role: LiveChatMirroredMessage['role'] = node.classList.contains('user')
      ? 'user'
      : node.classList.contains('assistant')
        ? 'assistant'
        : 'system';
    const text = chatMessages.length
      ? node.querySelector<HTMLElement>('.assistant-chat-bubble > p')?.textContent?.trim() ?? ''
      : Array.from(node.childNodes)
        .filter((child) => child.nodeType === Node.TEXT_NODE)
        .map((child) => child.textContent ?? '')
        .join(' ')
        .trim();
    const label = node.querySelector<HTMLElement>('strong')?.textContent?.trim()
      || (role === 'user' ? 'You' : role === 'assistant' ? 'Assistant' : 'System');
    const timestamp = node.querySelector<HTMLTimeElement>('time')?.dateTime || null;
    return {
      id: `${role}:${timestamp ?? 'untimed'}:${index}:${text.slice(0, 24)}`,
      role,
      label,
      text,
      timestamp,
    };
  }).filter((message) => Boolean(message.text));
}

/** Mirrors the avatar bridge's rendered output; the bridge remains the only animation owner. */
export function readLiveChatMirroredAvatar(root: ParentNode = document): LiveChatMirroredAvatar {
  const host = root.querySelector<HTMLElement>('.assistant-live-character-avatar');
  const image = host?.querySelector<HTMLImageElement>('img') ?? null;
  return {
    imageUrl: image?.currentSrc || image?.src || null,
    alt: image?.alt || 'Live assistant avatar',
    backgroundImage: host?.style.backgroundImage || '',
    mouthFrame: host?.dataset.mouthFrame || 'closed',
    voiceMode: host?.dataset.voiceMode || 'idle',
  };
}

/** Delegates text submission to the existing ChatbotWorkspace composer and mutation owner. */
export function submitLiveChatMessageThroughExistingComposer(
  text: string,
  root: ParentNode = document,
): boolean {
  const value = text.trim();
  if (!value) return false;
  const textarea = root.querySelector<HTMLTextAreaElement>('.assistant-composer textarea');
  const form = textarea?.closest<HTMLFormElement>('form.assistant-composer');
  if (!textarea || !form) return false;

  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  if (setter) setter.call(textarea, value);
  else textarea.value = value;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));
  if (typeof form.requestSubmit === 'function') form.requestSubmit();
  else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  return true;
}
