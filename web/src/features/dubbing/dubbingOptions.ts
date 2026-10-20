/** Languages a dub can go between: what Parakeet-TDT transcribes and the TTS engines speak. */
export const DUB_LANGUAGES = [
  { code: 'en', label: 'English' }, { code: 'es', label: 'Spanish' }, { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' }, { code: 'it', label: 'Italian' }, { code: 'pt', label: 'Portuguese' },
  { code: 'nl', label: 'Dutch' }, { code: 'pl', label: 'Polish' }, { code: 'ru', label: 'Russian' },
  { code: 'uk', label: 'Ukrainian' }, { code: 'sv', label: 'Swedish' }, { code: 'da', label: 'Danish' },
  { code: 'fi', label: 'Finnish' }, { code: 'cs', label: 'Czech' }, { code: 'el', label: 'Greek' },
] as const;

/**
 * Who translates. The workspace's chat model is whatever Settings selects (it may be a cloud model);
 * the named cloud models always send the transcript out.
 */
export const TRANSLATORS = [
  { id: '', label: 'Chat model from Settings', cloud: false },
  { id: 'lmstudio', label: 'LM Studio (local)', cloud: false },
  { id: 'llamacpp', label: 'llama.cpp (local)', cloud: false },
  { id: 'openrouter', label: 'OpenRouter (cloud)', cloud: true },
  { id: 'cerebras', label: 'Cerebras (cloud)', cloud: true },
] as const;

export const FIT_LABELS: Record<string, string> = {
  pending: 'No take yet',
  fits: 'Fits',
  stretched: 'Fits (stretched)',
  shortened: 'Fits (shortened)',
  over: 'Too long',
  short: 'Short',
};

export function formatTime(seconds: number): string {
  const whole = Math.max(0, seconds);
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${(whole - minutes * 60).toFixed(1).padStart(4, '0')}`;
}
