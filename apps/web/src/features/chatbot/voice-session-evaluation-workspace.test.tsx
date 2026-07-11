import { screen, waitFor } from '@testing-library/dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./VoiceSessionEvaluationPanel', () => ({
  VoiceSessionEvaluationPanel: () => <div>Durable voice evidence panel</div>,
}));

import {
  initializeVoiceSessionEvaluationWorkspace,
  mountVoiceSessionEvaluation,
} from './voice-session-evaluation-workspace';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('voice session evaluation workspace', () => {
  it('mounts once inside the existing Voice Sessions view', async () => {
    document.body.innerHTML = '<section aria-label="Voice Sessions view"><h2>Voice Sessions</h2></section>';
    const dispose = initializeVoiceSessionEvaluationWorkspace();

    expect(mountVoiceSessionEvaluation()).toBeTruthy();
    expect(document.querySelectorAll('[data-omnix-voice-session-evaluation-host]')).toHaveLength(1);
    await waitFor(() => expect(screen.getByText('Durable voice evidence panel')).toBeInTheDocument());
    expect(mountVoiceSessionEvaluation()).toBe(document.querySelector('[data-omnix-voice-session-evaluation-host]'));

    dispose();
    expect(document.querySelector('[data-omnix-voice-session-evaluation-host]')).toBeNull();
  });

  it('removes conversation evidence when navigating away from Voice Sessions', async () => {
    document.body.innerHTML = '<section aria-label="Voice Sessions view"><h2>Voice Sessions</h2></section>';
    const dispose = initializeVoiceSessionEvaluationWorkspace();

    await waitFor(() => expect(screen.getByText('Durable voice evidence panel')).toBeInTheDocument());
    document.querySelector('section')?.setAttribute('aria-label', 'Characters view');
    mountVoiceSessionEvaluation();

    expect(document.querySelector('[data-omnix-voice-session-evaluation-host]')).toBeNull();
    expect(screen.queryByText('Durable voice evidence panel')).not.toBeInTheDocument();
    dispose();
  });
});
