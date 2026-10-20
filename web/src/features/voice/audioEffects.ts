/**
 * Voice Studio's effects, as the stable ids the backend chain applies once to the whole take
 * (`platform/voice/effects.py`). Display labels saved before effects worked count as off.
 */
export const AUDIO_EFFECTS = [
  { id: 'eq', label: 'Equalizer', description: 'Cuts rumble below 80 Hz and adds presence above 3 kHz.' },
  { id: 'deesser', label: 'De-esser', description: 'Tames harsh “s” sounds (5–9 kHz) when they get loud.' },
  { id: 'compressor', label: 'Compression', description: 'Evens out loud and quiet passages.' },
  { id: 'reverb', label: 'Reverb', description: 'A short room; the take gets a natural tail.' },
] as const;

export type AudioEffectId = (typeof AUDIO_EFFECTS)[number]['id'];

const EFFECT_IDS = new Set<string>(AUDIO_EFFECTS.map((effect) => effect.id));

/** Only stable ids, in chain order. */
export function effectIds(values: readonly string[] | undefined): AudioEffectId[] {
  const chosen = new Set(values ?? []);
  return AUDIO_EFFECTS.map((effect) => effect.id).filter((id) => chosen.has(id) && EFFECT_IDS.has(id));
}

export const EXPORT_FORMATS = [
  { id: 'wav16', label: 'WAV 16-bit' },
  { id: 'wav24', label: 'WAV 24-bit' },
  { id: 'flac', label: 'FLAC' },
  { id: 'mp3', label: 'MP3 (VBR)' },
  { id: 'opus', label: 'Opus' },
] as const;
export type ExportFormatId = (typeof EXPORT_FORMATS)[number]['id'];

const SAMPLE_RATES = [16000, 22050, 24000, 44100, 48000];
const OPUS_SAMPLE_RATES = [8000, 12000, 16000, 24000, 48000];

/** The rates a format can be exported at; Opus only runs at its own fixed rates. */
export function exportSampleRates(format: ExportFormatId): number[] {
  return format === 'opus' ? OPUS_SAMPLE_RATES : SAMPLE_RATES;
}

export const LOUDNESS_PRESETS = [
  { id: 'none', label: 'Keep level' },
  { id: 'podcast', label: 'Podcast (−16 LUFS)' },
  { id: 'broadcast', label: 'Broadcast (−23 LUFS)' },
] as const;
export type LoudnessPresetId = (typeof LOUDNESS_PRESETS)[number]['id'];

/** Delivery instructions offered as suggestions; any text works on engines that read instructions. */
export const DELIVERY_SUGGESTIONS = ['Calm', 'Warm', 'Enthusiastic', 'Whispering', 'Deep, authoritative', 'Narrator, clear'];
