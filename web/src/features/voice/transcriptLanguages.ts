/**
 * Languages the timed transcription engine (Parakeet-TDT v3) transcribes. It
 * detects the language itself; the choice is recorded on the transcript and
 * used by subtitles and dubbing.
 */
export const TRANSCRIPT_LANGUAGES = [
  { code: '', label: 'Detect automatically' },
  { code: 'en', label: 'English' },
  { code: 'bg', label: 'Bulgarian' },
  { code: 'hr', label: 'Croatian' },
  { code: 'cs', label: 'Czech' },
  { code: 'da', label: 'Danish' },
  { code: 'nl', label: 'Dutch' },
  { code: 'et', label: 'Estonian' },
  { code: 'fi', label: 'Finnish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'el', label: 'Greek' },
  { code: 'hu', label: 'Hungarian' },
  { code: 'it', label: 'Italian' },
  { code: 'lv', label: 'Latvian' },
  { code: 'lt', label: 'Lithuanian' },
  { code: 'mt', label: 'Maltese' },
  { code: 'pl', label: 'Polish' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'ro', label: 'Romanian' },
  { code: 'ru', label: 'Russian' },
  { code: 'sk', label: 'Slovak' },
  { code: 'sl', label: 'Slovenian' },
  { code: 'es', label: 'Spanish' },
  { code: 'sv', label: 'Swedish' },
  { code: 'uk', label: 'Ukrainian' },
] as const;

/** A known language code, or '' (detect) for anything else. */
export function transcriptLanguage(code: string | null | undefined): string {
  const normalized = (code ?? '').trim().toLowerCase().split(/[-_]/)[0];
  return TRANSCRIPT_LANGUAGES.some((entry) => entry.code === normalized) ? normalized : '';
}
