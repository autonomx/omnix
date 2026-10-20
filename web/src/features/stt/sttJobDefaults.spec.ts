import { describe, expect, it } from 'vitest';
import { buildSttInputPayload, buildSttStages, type SttModuleDefaults } from './sttJobDefaults';

const defaults: SttModuleDefaults = {
  providerId: 'parakeet',
  language: 'en',
  saveTranscript: true,
};

describe('STT default request helpers', () => {
  it('sends a stored asset and the central provider, never a server path', () => {
    const payload = buildSttInputPayload({ providerId: '', audioAssetId: 'asset:audio', language: 'de' }, defaults);
    expect(payload).toEqual({
      asset_id: 'asset:audio', provider_id: 'parakeet', save_transcript: true, timed: true, diarize: false, language: 'de',
    });
    expect(payload).not.toHaveProperty('source_path');
    expect(payload).not.toHaveProperty('alignment');
  });

  it('preserves an explicit per-job provider', () => {
    expect(buildSttInputPayload({ providerId: 'remote-stt', audioAssetId: 'asset:audio', language: '' }, defaults)).toMatchObject({ provider_id: 'remote-stt' });
  });

  it('stores the transcript only when central defaults ask for it', () => {
    expect(buildSttStages(defaults).map((stage) => stage.id)).toEqual(['transcribe', 'store-transcript']);
    expect(buildSttStages({ ...defaults, saveTranscript: false }).map((stage) => stage.id)).toEqual(['transcribe']);
  });
});
