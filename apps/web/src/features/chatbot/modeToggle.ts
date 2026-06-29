const STORAGE_KEY = 'omnix.chat.mode';
const INSTALLED_KEY = '__omnix_chat_mode_toggle__';
const BUTTON_CLASS = 'omnix-chat-mode-toggle';

type AnyWindow = Window & Record<string, unknown>;

function isEnabled(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'agent';
  } catch {
    return false;
  }
}

function setEnabled(value: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, value ? 'agent' : 'normal');
  } catch {
    // optional storage
  }
}

function paint(button: HTMLButtonElement): void {
  const enabled = isEnabled();
  button.textContent = enabled ? 'Agent Chat: On' : 'Agent Chat: Off';
  button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
  button.style.border = enabled ? '1px solid rgba(94, 234, 212, 0.75)' : '1px solid rgba(255, 255, 255, 0.18)';
  button.style.borderRadius = '999px';
  button.style.background = enabled ? 'rgba(20, 184, 166, 0.22)' : 'rgba(255, 255, 255, 0.08)';
  button.style.color = 'inherit';
  button.style.cursor = 'pointer';
  button.style.fontWeight = '700';
  button.style.padding = '0.42rem 0.7rem';
}

function makeButton(): HTMLButtonElement {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = BUTTON_CLASS;
  button.addEventListener('click', () => {
    setEnabled(!isEnabled());
    document.querySelectorAll<HTMLButtonElement>(`.${BUTTON_CLASS}`).forEach(paint);
  });
  paint(button);
  return button;
}

function mount(): void {
  const header = document.querySelector('.assistant-chat-header-actions');
  if (header && !header.querySelector(`.${BUTTON_CLASS}`)) header.prepend(makeButton());
  const controls = document.querySelector('.assistant-composer-controls');
  if (controls && !controls.querySelector(`.${BUTTON_CLASS}`)) controls.appendChild(makeButton());
}

function watch(): void {
  mount();
  const observer = new MutationObserver(mount);
  observer.observe(document.body, { childList: true, subtree: true });
}

export function installModeToggle(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const w = window as unknown as AnyWindow;
  if (w[INSTALLED_KEY]) return;
  w[INSTALLED_KEY] = true;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch, { once: true });
  else watch();
}

installModeToggle();
