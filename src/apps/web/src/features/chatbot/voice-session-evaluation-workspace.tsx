import { createRoot, type Root } from 'react-dom/client';

import { VoiceSessionEvaluationPanel } from './VoiceSessionEvaluationPanel';

const HOST_ATTRIBUTE = 'data-omnix-voice-session-evaluation-host';

type VoiceEvaluationWindow = Window & typeof globalThis & {
  __omnixVoiceSessionEvaluationWorkspaceInstalled?: boolean;
};

let mountedRoot: Root | null = null;
let mountedHost: HTMLElement | null = null;

export function initializeVoiceSessionEvaluationWorkspace(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const liveWindow = window as VoiceEvaluationWindow;
  if (liveWindow.__omnixVoiceSessionEvaluationWorkspaceInstalled) return () => undefined;
  liveWindow.__omnixVoiceSessionEvaluationWorkspaceInstalled = true;

  const observer = new MutationObserver(() => mountVoiceSessionEvaluation());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  mountVoiceSessionEvaluation();

  return () => {
    observer.disconnect();
    disposeMountedPanel();
    liveWindow.__omnixVoiceSessionEvaluationWorkspaceInstalled = false;
  };
}

export function mountVoiceSessionEvaluation(root: ParentNode = document): HTMLElement | null {
  if (mountedHost && !mountedHost.isConnected) disposeMountedPanel();
  const view = root.querySelector<HTMLElement>('[aria-label="Voice Sessions view"]');
  if (!view) {
    disposeMountedPanel();
    return null;
  }
  const existing = view.querySelector<HTMLElement>(`[${HOST_ATTRIBUTE}]`);
  if (existing) return existing;

  mountedHost = document.createElement('div');
  mountedHost.setAttribute(HOST_ATTRIBUTE, 'true');
  view.appendChild(mountedHost);
  mountedRoot = createRoot(mountedHost);
  mountedRoot.render(<VoiceSessionEvaluationPanel />);
  return mountedHost;
}

function disposeMountedPanel(): void {
  mountedRoot?.unmount();
  mountedRoot = null;
  mountedHost?.remove();
  mountedHost = null;
}
