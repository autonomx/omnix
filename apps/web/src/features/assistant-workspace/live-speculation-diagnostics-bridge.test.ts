import { describe, expect, it } from 'vitest';

import { isSpeculationDiagnosticStage } from './live-speculation-diagnostics-bridge';

describe('live speculation diagnostics bridge', () => {
  it('records both LLM speculation and speculative TTS timing stages', () => {
    expect(isSpeculationDiagnosticStage('llm_speculation_reused')).toBe(true);
    expect(isSpeculationDiagnosticStage('tts_speculative_prefetch_started')).toBe(true);
    expect(isSpeculationDiagnosticStage('tts_speculative_prefetch_accepted')).toBe(true);
    expect(isSpeculationDiagnosticStage('tts_first_pcm_frame_sent')).toBe(false);
    expect(isSpeculationDiagnosticStage('stt_endpoint_candidate')).toBe(false);
  });
});
