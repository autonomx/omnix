import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { LIVE_COORDINATION_TERMINAL_EVENT } from './live-session-coordinator';
import {
  initializeLiveVoiceTranscriptReconciliation,
  removeTransientFinalUserRows,
  resetLiveVoiceTranscriptReconciliationForTests,
} from './live-voice-transcript-reconciliation';

describe('live voice transcript reconciliation', () => {
  let dispose: () => void;

  beforeEach(() => {
    resetLiveVoiceTranscriptReconciliationForTests();
    document.body.innerHTML = `
      <div class="assistant-voice-transcript">
        <p class="user" data-live-voice-id="live-voice-123"><span><strong>You</strong></span>I'm the one that found you.</p>
        <p class="user"><span><strong>You</strong></span>I'm the one that found you.</p>
      </div>
    `;
    dispose = initializeLiveVoiceTranscriptReconciliation();
  });

  afterEach(() => {
    dispose?.();
    resetLiveVoiceTranscriptReconciliationForTests();
    document.body.innerHTML = '';
  });

  it('removes only the controller-created final row after durable conversation submission', () => {
    window.dispatchEvent(new CustomEvent(LIVE_COORDINATION_TERMINAL_EVENT, {
      detail: { outcome: 'conversation_submitted' },
    }));

    expect(document.querySelectorAll('.assistant-voice-transcript p.user')).toHaveLength(1);
    expect(document.querySelector('.assistant-voice-transcript p.user[data-live-voice-id]')).toBeNull();
    expect(document.querySelector('.assistant-voice-transcript p.user')?.textContent).toContain("I'm the one that found you.");
  });

  it('keeps transient rows for non-conversation terminal outcomes', () => {
    window.dispatchEvent(new CustomEvent(LIVE_COORDINATION_TERMINAL_EVENT, {
      detail: { outcome: 'control_executed' },
    }));

    expect(document.querySelectorAll('.assistant-voice-transcript p.user')).toHaveLength(2);
  });

  it('does not remove the active draft row', () => {
    document.querySelector('.assistant-voice-transcript')?.insertAdjacentHTML(
      'beforeend',
      '<p class="user" data-live-voice-id="live-voice-draft">still speaking</p>',
    );

    expect(removeTransientFinalUserRows(document)).toBe(1);
    expect(document.querySelector('[data-live-voice-id="live-voice-draft"]')).not.toBeNull();
  });
});
