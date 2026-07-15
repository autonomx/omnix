import { DESKTOP_COMPANION_TEXT_EVENT } from './desktop-companion-delivery';

const ATTRIBUTE = 'data-omnix-desktop-companion-text';

type TextSurfaceWindow = Window & typeof globalThis & {
  __omnixDesktopCompanionTextSurfaceInstalled?: boolean;
};

export type DesktopCompanionTextNotice = {
  sessionId: string;
  observationId: string;
  turnId: string;
  content: string;
  priority: 'normal' | 'critical';
  expiresAtMs: number;
};

let latest: DesktopCompanionTextNotice | null = null;

export function initializeDesktopCompanionTextSurface(root: ParentNode = document): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const target = window as TextSurfaceWindow;
  if (target.__omnixDesktopCompanionTextSurfaceInstalled) return () => undefined;
  target.__omnixDesktopCompanionTextSurfaceInstalled = true;
  const ensure = () => ensureSurface(root);
  const handleText = (event: Event) => {
    const notice = normalizeDesktopCompanionTextNotice((event as CustomEvent<unknown>).detail);
    if (!notice) return;
    latest = notice;
    ensureSurface(root);
    render(root);
  };
  const observer = new MutationObserver(ensure);
  observer.observe(root instanceof Document ? root.documentElement : root, { childList: true, subtree: true });
  window.addEventListener(DESKTOP_COMPANION_TEXT_EVENT, handleText);
  ensure();
  return () => {
    observer.disconnect();
    window.removeEventListener(DESKTOP_COMPANION_TEXT_EVENT, handleText);
    root.querySelectorAll(`[${ATTRIBUTE}]`).forEach((element) => element.remove());
    latest = null;
    target.__omnixDesktopCompanionTextSurfaceInstalled = false;
  };
}

export function normalizeDesktopCompanionTextNotice(value: unknown): DesktopCompanionTextNotice | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  const sessionId = typeof input.sessionId === 'string' ? input.sessionId.trim() : '';
  const observationId = typeof input.observationId === 'string' ? input.observationId.trim() : '';
  const turnId = typeof input.turnId === 'string' ? input.turnId.trim() : '';
  const content = typeof input.content === 'string' ? input.content.replace(/\s+/g, ' ').trim().slice(0, 500) : '';
  const expiresAtMs = Number(input.expiresAtMs);
  if (!sessionId || !observationId || !turnId || !content || !Number.isFinite(expiresAtMs)) return null;
  return {
    sessionId,
    observationId,
    turnId,
    content,
    expiresAtMs,
    priority: input.priority === 'critical' ? 'critical' : 'normal',
  };
}

function ensureSurface(root: ParentNode): void {
  const host = root.querySelector<HTMLElement>('.assistant-audio-devices');
  if (!host || host.querySelector(`[${ATTRIBUTE}]`)) return;
  const panel = document.createElement('section');
  panel.className = 'desktop-companion-text-surface';
  panel.setAttribute(ATTRIBUTE, 'true');
  panel.hidden = true;
  const header = document.createElement('div');
  header.className = 'desktop-companion-text-surface__header';
  const title = document.createElement('strong');
  title.textContent = 'Companion';
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.textContent = 'Dismiss';
  dismiss.addEventListener('click', () => {
    latest = null;
    render(root);
  });
  header.append(title, dismiss);
  const content = document.createElement('p');
  content.className = 'desktop-companion-text-surface__content';
  panel.append(header, content);
  host.append(panel);
  render(root);
}

function render(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>(`[${ATTRIBUTE}]`).forEach((panel) => {
    const visible = Boolean(latest && Date.now() < latest.expiresAtMs);
    panel.hidden = !visible;
    panel.dataset.priority = latest?.priority ?? 'normal';
    const content = panel.querySelector<HTMLElement>('.desktop-companion-text-surface__content');
    if (content) content.textContent = visible ? latest?.content ?? '' : '';
  });
}
