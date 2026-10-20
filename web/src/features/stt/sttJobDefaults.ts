export type SttJobFormValues = {
  providerId: string;
  audioAssetId: string;
  language: string;
};

export type SttModuleDefaults = {
  providerId: string;
  language: string;
  saveTranscript: boolean;
};

/**
 * An `stt.transcribe` request: a stored audio asset only, never a server path (a path in a
 * job would let a request read any file on the worker). Batch transcription runs on the
 * timed, multilingual engine (Parakeet-TDT), not the English-only live path; speaker labels
 * belong to Voice Studio's Transcribe tool. The language is recorded on the transcript.
 */
export function buildSttInputPayload(values: SttJobFormValues, defaults: SttModuleDefaults) {
  return {
    asset_id: values.audioAssetId || null,
    provider_id: values.providerId || defaults.providerId || null,
    save_transcript: defaults.saveTranscript,
    timed: true,
    diarize: false,
    language: values.language,
  };
}

export function buildSttStages(defaults: SttModuleDefaults) {
  return [
    { id: 'transcribe', label: 'Transcribe audio', resource_class: 'gpu:stt' as const, status: 'queued' as const },
    ...(defaults.saveTranscript
      ? [{ id: 'store-transcript', label: 'Store transcript asset', resource_class: 'cpu' as const, status: 'queued' as const }]
      : []),
  ];
}
