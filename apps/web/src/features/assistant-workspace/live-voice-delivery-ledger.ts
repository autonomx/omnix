import type { LiveCallDiagnosticsReporter } from './live-call-diagnostics-client';

const PCM_SAMPLES_PER_MS = 24;
const DELIVERY_ROW_ATTRIBUTE = 'data-omnix-live-delivery';

export type LiveVoiceDeliveryPhrase = {
  phraseIndex: number;
  text: string;
  textStart: number;
  textEnd: number;
  audioSampleStart: number | null;
  audioSampleEnd: number | null;
};

export type LiveVoiceDeliveryLedger = {
  assistantTurnId: string | null;
  generatedText: string;
  phrases: LiveVoiceDeliveryPhrase[];
  audioPlayedSamples: number;
  audioDeliveredPhraseCount: number;
  activePhraseIndex: number | null;
  visualDeliveredTextEnd: number;
  contextDeliveredTextEnd: number;
};

export function createLiveVoiceDeliveryLedger(): LiveVoiceDeliveryLedger {
  return {
    assistantTurnId: null,
    generatedText: '',
    phrases: [],
    audioPlayedSamples: 0,
    audioDeliveredPhraseCount: 0,
    activePhraseIndex: null,
    visualDeliveredTextEnd: 0,
    contextDeliveredTextEnd: 0,
  };
}

export function appendDeliveryPhrase(
  ledger: LiveVoiceDeliveryLedger,
  phraseIndex: number,
  text: string,
): void {
  const normalized = text.trim();
  const separator = ledger.generatedText ? ' ' : '';
  const textStart = ledger.generatedText.length + separator.length;
  ledger.generatedText = `${ledger.generatedText}${separator}${normalized}`;
  ledger.phrases.push({
    phraseIndex,
    text: normalized,
    textStart,
    textEnd: ledger.generatedText.length,
    audioSampleStart: null,
    audioSampleEnd: null,
  });
}

export function handleDeliveryDiagnostic(
  ledger: LiveVoiceDeliveryLedger,
  event: string,
  details: Record<string, unknown>,
): boolean {
  if (event === 'phrase_buffered') {
    const phraseIndex = finiteNumber(details.phrase_index, -1);
    const phrase = ledger.phrases.find((item) => item.phraseIndex === phraseIndex);
    if (!phrase) return false;
    phrase.audioSampleStart = ledger.phrases[phraseIndex - 1]?.audioSampleEnd ?? 0;
    phrase.audioSampleEnd = phrase.audioSampleStart
      + Math.max(1, Math.round(finiteNumber(details.audio_ms, 0) * PCM_SAMPLES_PER_MS));
    return advanceDeliveryLedger(ledger, ledger.audioPlayedSamples);
  }
  if (!event.startsWith('worklet_')) return false;
  return advanceDeliveryLedger(
    ledger,
    finiteNumber(details.played_samples, ledger.audioPlayedSamples),
  );
}

export function advanceDeliveryLedger(
  ledger: LiveVoiceDeliveryLedger,
  playedSamples: number,
): boolean {
  const finalSample = ledger.phrases.at(-1)?.audioSampleEnd ?? ledger.audioPlayedSamples;
  const boundedSamples = playedSamples === Number.MAX_SAFE_INTEGER
    ? finalSample
    : playedSamples;
  ledger.audioPlayedSamples = Number.isFinite(boundedSamples)
    ? Math.max(ledger.audioPlayedSamples, boundedSamples)
    : ledger.audioPlayedSamples;
  let changed = false;
  for (const phrase of ledger.phrases) {
    if (phrase.audioSampleStart === null || phrase.audioSampleEnd === null) continue;
    if (ledger.audioPlayedSamples > phrase.audioSampleStart && ledger.visualDeliveredTextEnd < phrase.textEnd) {
      ledger.visualDeliveredTextEnd = phrase.textEnd;
      ledger.activePhraseIndex = phrase.phraseIndex;
      changed = true;
    }
    if (ledger.audioPlayedSamples >= phrase.audioSampleEnd && ledger.contextDeliveredTextEnd < phrase.textEnd) {
      ledger.contextDeliveredTextEnd = phrase.textEnd;
      ledger.audioDeliveredPhraseCount = Math.max(ledger.audioDeliveredPhraseCount, phrase.phraseIndex + 1);
      ledger.activePhraseIndex = null;
      changed = true;
    }
  }
  return changed;
}

export function renderDeliveryLedger(
  ledger: LiveVoiceDeliveryLedger,
  partial = false,
): void {
  const host = document.querySelector<HTMLElement>('.assistant-voice-transcript');
  if (!host || ledger.visualDeliveredTextEnd <= 0) return;
  let row = host.querySelector<HTMLElement>(`[${DELIVERY_ROW_ATTRIBUTE}]`);
  if (!row) {
    row = document.createElement('p');
    row.setAttribute(DELIVERY_ROW_ATTRIBUTE, 'true');
    row.className = 'assistant';
    host.appendChild(row);
  }
  const visible = ledger.generatedText.slice(0, ledger.visualDeliveredTextEnd).trim();
  row.textContent = partial ? `Assistant: ${visible} [partial]` : `Assistant: ${visible}`;
}

export function removeDeliveryLedgerRow(): void {
  document.querySelector(`[${DELIVERY_ROW_ATTRIBUTE}]`)?.remove();
}

export function instrumentDeliveryReporter(
  reporter: LiveCallDiagnosticsReporter,
  getLedger: () => LiveVoiceDeliveryLedger | null,
  onChanged: (ledger: LiveVoiceDeliveryLedger) => void,
): void {
  const record = reporter.record.bind(reporter);
  reporter.record = (event, details = {}, source = 'browser') => {
    record(event, details, source);
    const ledger = getLedger();
    if (ledger && handleDeliveryDiagnostic(ledger, event, details)) onChanged(ledger);
  };
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}
