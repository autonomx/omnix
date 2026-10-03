import { createRoot, type Root } from 'react-dom/client';

import { VoiceSessionEvaluationPanel } from './VoiceSessionEvaluationPanel';

let voiceSessionEvaluationWorkspaceInstalled = false;

const HOST_ATTRIBUTE = 'data-omnix-voice-session-evaluation-host';

let mountedRoot: Root | null = null;
let mountedHost: HTMLElement | null = null;

export function initializeVoiceSessionEvaluationWorkspace(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  if (voiceSessionEvaluationWorkspaceInstalled) return () => undefined;
  voiceSessionEvaluationWorkspaceInstalled = true;

  const observer = new MutationObserver(() => mountVoiceSessionEvaluation());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  mountVoiceSessionEvaluation();

  return () => {
    observer.disconnect();
    disposeMountedPanel();
    voiceSessionEvaluationWorkspaceInstalled = false;
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
