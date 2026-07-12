import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  beginRpgTurnDiagnostics,
  completeRpgTurnDiagnostics,
  copyRpgTurnDiagnostics,
  markRpgTurnReactCommitted,
  markRpgTurnVisible,
  resetRpgTurnDiagnosticsForTests,
  serializeRpgTurnDiagnostics,
} from './rpgTurnDiagnostics';

afterEach(() => {
  resetRpgTurnDiagnosticsForTests();
  vi.restoreAllMocks();
});

describe('rpgTurnDiagnostics evidence export', () => {
  it('serializes completed browser timing samples for the local acceptance validator', () => {
    beginRpgTurnDiagnostics('session:bran', 'submit:one', 10);
    completeRpgTurnDiagnostics({
      sessionId: 'session:bran',
      submissionId: 'submit:one',
      interactionId: 'interaction:1',
      traceId: 'trace:1',
      responseHeaders: new Headers({
        'X-Omnix-Rpg-Response-Bytes': '500',
        'X-Omnix-Rpg-Attribution-Pct': '98',
      }),
      milestones: {
        requestStartedMs: 10,
        headersReceivedMs: 20,
        bodyReadMs: 25,
        jsonParsedMs: 27,
        storeUpdatedMs: 30,
      },
    });
    vi.spyOn(performance, 'now').mockReturnValueOnce(35).mockReturnValueOnce(42);
    markRpgTurnReactCommitted('session:bran', ['interaction:1']);
    markRpgTurnVisible('session:bran', ['interaction:1']);

    const payload = JSON.parse(serializeRpgTurnDiagnostics('session:bran'));

    expect(payload.format_version).toBe('rpg_browser_timing_evidence_v1');
    expect(payload.session_id).toBe('session:bran');
    expect(payload.samples).toHaveLength(1);
    expect(payload.samples[0].interactionId).toBe('interaction:1');
    expect(payload.samples[0].client.commitToVisibleMs).toBe(7);
  });

  it('copies the exported JSON when the clipboard API is available', async () => {
    beginRpgTurnDiagnostics('session:bran', 'submit:one', 10);
    const writeText = vi.fn(async (_value: string) => undefined);
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    await expect(copyRpgTurnDiagnostics('session:bran')).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledOnce();
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('rpg_browser_timing_evidence_v1'));
  });
});
