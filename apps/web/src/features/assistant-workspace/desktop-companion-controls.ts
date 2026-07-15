import { desktopCompanionControlStore } from './desktop-companion-control-store';
import { DESKTOP_COMPANION_STATUS_EVENT } from './desktop-companion-watch-controller';

const ATTRIBUTE = 'data-omnix-desktop-companion-controls';

type ControlsWindow = Window & typeof globalThis & {
  __omnixDesktopCompanionControlsInstalled?: boolean;
};

type StatusDetail = {
  phase?: string;
  reason?: string;
  reaction?: string | null;
};

let latestStatus: StatusDetail = { phase: 'off', reason: 'not_started' };

export function initializeDesktopCompanionControls(root: ParentNode = document): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const target = window as ControlsWindow;
  if (target.__omnixDesktopCompanionControlsInstalled) return () => undefined;
  target.__omnixDesktopCompanionControlsInstalled = true;
  const inject = () => ensureControls(root);
  inject();
  const observer = new MutationObserver(inject);
  observer.observe(root instanceof Document ? root.documentElement : root, { childList: true, subtree: true });
  const unsubscribe = desktopCompanionControlStore.subscribe(() => render(root));
  const handleStatus = (event: Event) => {
    latestStatus = (event as CustomEvent<StatusDetail>).detail ?? {};
    render(root);
  };
  window.addEventListener(DESKTOP_COMPANION_STATUS_EVENT, handleStatus);
  return () => {
    observer.disconnect();
    unsubscribe();
    window.removeEventListener(DESKTOP_COMPANION_STATUS_EVENT, handleStatus);
    root.querySelectorAll(`[${ATTRIBUTE}]`).forEach((element) => element.remove());
    target.__omnixDesktopCompanionControlsInstalled = false;
  };
}

function ensureControls(root: ParentNode): void {
  const host = root.querySelector<HTMLElement>('.assistant-audio-devices');
  if (!host || host.querySelector(`[${ATTRIBUTE}]`)) return;
  const row = document.createElement('div');
  row.className = 'desktop-companion-controls';
  row.setAttribute(ATTRIBUTE, 'true');

  const title = document.createElement('span');
  title.className = 'desktop-companion-controls__title';
  title.textContent = 'Companion Watch';
  const status = document.createElement('strong');
  status.className = 'desktop-companion-controls__status';

  const actions = document.createElement('div');
  actions.className = 'desktop-companion-controls__actions';
  actions.append(
    button('Start', 'desktop-companion-start', () => desktopCompanionControlStore.dispatch('start')),
    button('Pause', 'desktop-companion-pause', () => {
      const state = desktopCompanionControlStore.getState();
      desktopCompanionControlStore.dispatch(state.paused ? 'resume' : 'pause');
    }),
    button('Muted', 'desktop-companion-mute', () => {
      const state = desktopCompanionControlStore.getState();
      desktopCompanionControlStore.dispatch(state.muted ? 'unmute' : 'mute');
    }),
    button('Stop', 'desktop-companion-stop', () => desktopCompanionControlStore.dispatch('stop')),
  );
  row.append(title, status, actions);
  host.append(row);
  render(root);
}

function render(root: ParentNode): void {
  const state = desktopCompanionControlStore.getState();
  root.querySelectorAll<HTMLElement>('.desktop-companion-controls__status').forEach((element) => {
    element.textContent = statusLabel(latestStatus.phase, latestStatus.reason);
    element.title = latestStatus.reason ?? '';
  });
  root.querySelectorAll<HTMLButtonElement>('.desktop-companion-start').forEach((element) => {
    element.disabled = state.requested;
    element.textContent = state.requested ? 'Watching' : 'Start';
  });
  root.querySelectorAll<HTMLButtonElement>('.desktop-companion-pause').forEach((element) => {
    element.disabled = !state.requested;
    element.textContent = state.paused ? 'Resume' : 'Pause';
  });
  root.querySelectorAll<HTMLButtonElement>('.desktop-companion-mute').forEach((element) => {
    element.disabled = !state.requested;
    element.textContent = state.muted ? 'Muted' : 'Sound on';
    element.setAttribute('aria-pressed', String(state.muted));
  });
  root.querySelectorAll<HTMLButtonElement>('.desktop-companion-stop').forEach((element) => {
    element.disabled = !state.requested;
  });
}

function button(label: string, className: string, action: () => void): HTMLButtonElement {
  const element = document.createElement('button');
  element.type = 'button';
  element.className = `desktop-companion-control ${className}`;
  element.textContent = label;
  element.addEventListener('click', action);
  return element;
}

export function statusLabel(phase = 'off', reason = ''): string {
  if (phase === 'analyzing') return 'Analyzing';
  if (phase === 'observation_ready') return 'Observed';
  if (phase === 'watching_idle') return 'Watching';
  if (phase === 'paused') return 'Paused';
  if (phase === 'backing_off') return 'Backoff';
  if (phase === 'error') return reason.includes('remote_vision_not_allowed') ? 'Remote blocked' : 'Error';
  if (reason === 'preflight_running') return 'Testing model';
  return 'Off';
}
