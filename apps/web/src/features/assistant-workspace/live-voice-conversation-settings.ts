export type ConversationPaceSetting = 'quick' | 'balanced' | 'reflective';
export type InterruptionPreference = 'easy' | 'balanced' | 'finish_more';
export type BackchannelMode = 'off' | 'minimal' | 'natural';

export type LiveConversationSettings = {
  conversationPace: ConversationPaceSetting;
  interruptionPreference: InterruptionPreference;
  backchannelMode: BackchannelMode;
};

const STORAGE_KEY = 'omnix.chatbot.assistantSettings';
const SETTINGS_HOST_SELECTOR = '.assistant-settings-list';
const CONTROLS_ATTRIBUTE = 'data-omnix-conversation-controls';

export const DEFAULT_LIVE_CONVERSATION_SETTINGS: LiveConversationSettings = {
  conversationPace: 'balanced',
  interruptionPreference: 'balanced',
  backchannelMode: 'off',
};

let initialized = false;

export function readLiveConversationSettings(): LiveConversationSettings {
  try {
    if (typeof window === 'undefined') return DEFAULT_LIVE_CONVERSATION_SETTINGS;
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}') as Record<string, unknown>;
    return {
      conversationPace: isConversationPace(parsed.conversationPace)
        ? parsed.conversationPace
        : DEFAULT_LIVE_CONVERSATION_SETTINGS.conversationPace,
      interruptionPreference: isInterruptionPreference(parsed.interruptionPreference)
        ? parsed.interruptionPreference
        : DEFAULT_LIVE_CONVERSATION_SETTINGS.interruptionPreference,
      backchannelMode: isBackchannelMode(parsed.backchannelMode)
        ? parsed.backchannelMode
        : DEFAULT_LIVE_CONVERSATION_SETTINGS.backchannelMode,
    };
  } catch {
    return DEFAULT_LIVE_CONVERSATION_SETTINGS;
  }
}

export function updateLiveConversationSettings(
  patch: Partial<LiveConversationSettings>,
): LiveConversationSettings {
  const current = readLiveConversationSettings();
  const next: LiveConversationSettings = {
    conversationPace: isConversationPace(patch.conversationPace)
      ? patch.conversationPace
      : current.conversationPace,
    interruptionPreference: isInterruptionPreference(patch.interruptionPreference)
      ? patch.interruptionPreference
      : current.interruptionPreference,
    backchannelMode: isBackchannelMode(patch.backchannelMode)
      ? patch.backchannelMode
      : current.backchannelMode,
  };
  try {
    if (typeof window !== 'undefined') {
      const existing = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}') as Record<string, unknown>;
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...existing, ...next }));
      window.dispatchEvent(new CustomEvent('omnix:live-conversation-settings-changed', { detail: next }));
    }
  } catch {
    // Settings remain usable for the current read even when storage is unavailable.
  }
  return next;
}

export function initializeLiveConversationSettingsControls(): void {
  if (initialized || typeof window === 'undefined' || typeof document === 'undefined') return;
  initialized = true;
  installControls();
  new MutationObserver(installControls).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
}

function installControls(): void {
  document.querySelectorAll<HTMLElement>(SETTINGS_HOST_SELECTOR).forEach((host) => {
    if (host.querySelector(`[${CONTROLS_ATTRIBUTE}]`)) return;
    const wrapper = document.createElement('div');
    wrapper.setAttribute(CONTROLS_ATTRIBUTE, 'true');
    wrapper.className = 'assistant-setting-item assistant-conversation-controls';
    const title = document.createElement('div');
    title.className = 'assistant-setting-copy';
    const strong = document.createElement('strong');
    strong.textContent = 'Live conversation behavior';
    const description = document.createElement('span');
    description.textContent = 'Control pause timing, interruption sensitivity, and optional spoken acknowledgements.';
    title.append(strong, description);
    const controls = document.createElement('div');
    controls.className = 'assistant-setting-control assistant-conversation-control-grid';
    const settings = readLiveConversationSettings();
    controls.append(
      createSelect('Conversation pace', 'conversationPace', settings.conversationPace, [
        ['quick', 'Quick'],
        ['balanced', 'Balanced'],
        ['reflective', 'Reflective'],
      ]),
      createSelect('Interruption behavior', 'interruptionPreference', settings.interruptionPreference, [
        ['easy', 'Easy to interrupt'],
        ['balanced', 'Balanced'],
        ['finish_more', 'Let assistant finish more often'],
      ]),
      createSelect('Spoken acknowledgements', 'backchannelMode', settings.backchannelMode, [
        ['off', 'Off'],
        ['minimal', 'Minimal'],
        ['natural', 'Natural'],
      ]),
    );
    wrapper.append(title, controls);
    host.append(wrapper);
  });
}

function createSelect<K extends keyof LiveConversationSettings>(
  labelText: string,
  key: K,
  selected: LiveConversationSettings[K],
  options: Array<[LiveConversationSettings[K], string]>,
): HTMLLabelElement {
  const label = document.createElement('label');
  label.className = 'assistant-conversation-control';
  const text = document.createElement('span');
  text.textContent = labelText;
  const select = document.createElement('select');
  select.setAttribute('aria-label', labelText);
  for (const [value, display] of options) {
    const option = document.createElement('option');
    option.value = String(value);
    option.textContent = display;
    option.selected = value === selected;
    select.append(option);
  }
  select.addEventListener('change', () => {
    updateLiveConversationSettings({ [key]: select.value } as Partial<LiveConversationSettings>);
  });
  label.append(text, select);
  return label;
}

function isConversationPace(value: unknown): value is ConversationPaceSetting {
  return value === 'quick' || value === 'balanced' || value === 'reflective';
}

function isInterruptionPreference(value: unknown): value is InterruptionPreference {
  return value === 'easy' || value === 'balanced' || value === 'finish_more';
}

function isBackchannelMode(value: unknown): value is BackchannelMode {
  return value === 'off' || value === 'minimal' || value === 'natural';
}

initializeLiveConversationSettingsControls();
