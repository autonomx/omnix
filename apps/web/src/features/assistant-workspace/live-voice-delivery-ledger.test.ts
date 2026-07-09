import { describe, expect, it } from 'vitest';

import {
  advanceDeliveryLedger,
  appendDeliveryPhrase,
  createLiveVoiceDeliveryLedger,
  handleDeliveryDiagnostic,
} from './live-voice-delivery-ledger';

describe('live voice delivery ledger', () => {
  it('keeps visual and conversational delivery separate', () => {
    const ledger = createLiveVoiceDeliveryLedger();
    appendDeliveryPhrase(ledger, 0, 'First delivered phrase.');
    appendDeliveryPhrase(ledger, 1, 'Second generated phrase.');

    handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 0, audio_ms: 1000 });
    handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 1, audio_ms: 1000 });

    expect(advanceDeliveryLedger(ledger, 1)).toBe(true);
    expect(ledger.visualDeliveredTextEnd).toBe(23);
    expect(ledger.contextDeliveredTextEnd).toBe(0);
    expect(ledger.activePhraseIndex).toBe(0);

    expect(advanceDeliveryLedger(ledger, 24_000)).toBe(true);
    expect(ledger.contextDeliveredTextEnd).toBe(23);
    expect(ledger.audioDeliveredPhraseCount).toBe(1);

    expect(advanceDeliveryLedger(ledger, 24_001)).toBe(true);
    expect(ledger.visualDeliveredTextEnd).toBe(48);
    expect(ledger.contextDeliveredTextEnd).toBe(23);
    expect(ledger.activePhraseIndex).toBe(1);
  });

  it('derives phrase sample ranges from streamed TTS diagnostics', () => {
    const ledger = createLiveVoiceDeliveryLedger();
    appendDeliveryPhrase(ledger, 0, 'One.');
    appendDeliveryPhrase(ledger, 1, 'Two.');

    handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 0, audio_ms: 500 });
    handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 1, audio_ms: 250 });

    expect(ledger.phrases[0]?.audioSampleStart).toBe(0);
    expect(ledger.phrases[0]?.audioSampleEnd).toBe(12_000);
    expect(ledger.phrases[1]?.audioSampleStart).toBe(12_000);
    expect(ledger.phrases[1]?.audioSampleEnd).toBe(18_000);
  });
});
