import { Button, Text } from '@mantine/core';
import { useState } from 'react';
import {
  AUDIO_EFFECTS,
  EXPORT_FORMATS,
  LOUDNESS_PRESETS,
  exportSampleRates,
  type AudioEffectId,
  type ExportFormatId,
  type LoudnessPresetId,
} from './audioEffects';
import type { DEFAULT_OUTPUT_SETTINGS } from './outputDefaults';
import type { TtsEnginesResponse } from './api/voiceClient';

export type OutputSettingName = keyof typeof DEFAULT_OUTPUT_SETTINGS;
type Engine = TtsEnginesResponse['engines'][number];

export interface ExportRequest {
  format: ExportFormatId;
  sampleRate: number | null;
  loudness: LoudnessPresetId;
}

export interface ExportedFile {
  id: string;
  title: string;
}

const EFFECTS_NOTICE_KEY = 'omnix.voice.effectsApplyNotice';

function effectsNoticeDismissed(): boolean {
  try {
    return window.localStorage.getItem(EFFECTS_NOTICE_KEY) === 'dismissed';
  } catch {
    return false;
  }
}

/** The right-hand inspector: the engine, delivery tuning, effects and export for the current take. */
export function VoiceInspector({
  engine,
  engineStatus,
  outputSettings,
  onSettingChange,
  onResetTuning,
  effects,
  onToggleEffect,
  onResetEffects,
  canExport,
  exportPending,
  exportError,
  exports,
  onExport,
}: {
  engine: Engine | undefined;
  engineStatus: string;
  outputSettings: Record<OutputSettingName, number>;
  onSettingChange: (name: OutputSettingName, value: number) => void;
  onResetTuning: () => void;
  effects: AudioEffectId[];
  onToggleEffect: (effect: AudioEffectId) => void;
  onResetEffects: () => void;
  canExport: boolean;
  exportPending: boolean;
  exportError: string;
  exports: ExportedFile[];
  onExport: (request: ExportRequest) => void;
}) {
  const [noticeHidden, setNoticeHidden] = useState(effectsNoticeDismissed);
  const [format, setFormat] = useState<ExportFormatId>('wav16');
  const [sampleRate, setSampleRate] = useState<string>('');
  const [loudness, setLoudness] = useState<LoudnessPresetId>('none');
  const rates = exportSampleRates(format);
  const rateValid = sampleRate === '' || rates.includes(Number(sampleRate));

  function dismissNotice() {
    setNoticeHidden(true);
    try {
      window.localStorage.setItem(EFFECTS_NOTICE_KEY, 'dismissed');
    } catch {
      // Blocked storage shows the notice again next time; nothing else depends on it.
    }
  }

  return (
    <aside className="voice-inspector" aria-label="Inspector">
      <section className="voice-inspector-section" aria-label="Engine">
        <h3>Engine</h3>
        <p className="voice-inspector-value">{engine?.label ?? 'No engine selected'}</p>
        {engineStatus ? <Text size="xs">{engineStatus}</Text> : null}
      </section>

      <section className="voice-inspector-section" aria-label="Delivery tuning">
        <div className="voice-inspector-heading"><h3>Delivery</h3><Button size="compact-xs" type="button" variant="subtle" onClick={onResetTuning}>Reset tuning</Button></div>
        <div className="voice-tuning">
          {(Object.entries(outputSettings) as [OutputSettingName, number][]).map(([name, value]) => {
            const unused = Boolean(engine && !engine.voice_controls.includes(name));
            return (
              <label key={name} title={unused ? `${engine?.label} has no equivalent setting; this slider is ignored.` : settingDescription(name)} className={unused ? 'enhancement-unused' : undefined}>
                <span>{settingLabel(name)}</span>
                <b>{unused ? 'Not used' : settingValueLabel(name, value)}</b>
                <input aria-label={`Output ${name}`} type="range" min={rangeMin(name)} max={rangeMax(name)} step={rangeStep(name)} value={value} disabled={unused} onChange={(event) => onSettingChange(name, Number(event.currentTarget.value))} />
              </label>
            );
          })}
        </div>
      </section>

      <section className="voice-inspector-section" aria-label="Effects">
        <div className="voice-inspector-heading"><h3>Effects</h3><Button size="compact-xs" type="button" variant="subtle" onClick={onResetEffects}>Reset effects</Button></div>
        {!noticeHidden ? (
          <div className="voice-notice" role="note">
            <span>Effects now apply to renders, once over the whole take. Effects saved before this change start off.</span>
            <Button size="compact-xs" variant="subtle" type="button" onClick={dismissNotice}>Got it</Button>
          </div>
        ) : null}
        <div className="effect-buttons">
          {AUDIO_EFFECTS.map((effect) => (
            <button aria-pressed={effects.includes(effect.id)} className={effects.includes(effect.id) ? 'active' : ''} key={effect.id} title={effect.description} type="button" onClick={() => onToggleEffect(effect.id)}>{effect.label}</button>
          ))}
        </div>
      </section>

      <section className="voice-inspector-section" aria-label="Export">
        <h3>Export</h3>
        <div className="voice-export-grid">
          <label>Format<select aria-label="Export format" value={format} onChange={(event) => { setFormat(event.currentTarget.value as ExportFormatId); setSampleRate(''); }}>{EXPORT_FORMATS.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}</select></label>
          <label>Sample rate<select aria-label="Export sample rate" value={sampleRate} onChange={(event) => setSampleRate(event.currentTarget.value)}>
            <option value="">{format === 'opus' ? '48 kHz (Opus)' : 'Original'}</option>
            {rates.map((rate) => <option key={rate} value={rate}>{(rate / 1000).toFixed(rate % 1000 ? 2 : 0)} kHz</option>)}
          </select></label>
          <label>Loudness<select aria-label="Export loudness" value={loudness} onChange={(event) => setLoudness(event.currentTarget.value as LoudnessPresetId)}>{LOUDNESS_PRESETS.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}</select></label>
        </div>
        <Button size="xs" type="button" disabled={!canExport || exportPending || !rateValid} loading={exportPending} onClick={() => onExport({ format, sampleRate: sampleRate ? Number(sampleRate) : null, loudness })}>Export take</Button>
        {!canExport ? <Text size="xs" className="voice-disabled-reason">Render or select a take to export it.</Text> : null}
        {exportError ? <Text size="xs" role="alert">{exportError}</Text> : null}
        {exports.length ? (
          <ul className="voice-export-list" aria-label="Exports">
            {exports.map((entry) => <li key={entry.id}><a href={`/api/assets/${encodeURIComponent(entry.id)}/download`} download>{entry.title}</a></li>)}
          </ul>
        ) : null}
      </section>
    </aside>
  );
}

function settingLabel(name: OutputSettingName): string {
  // "Style" is a sampling control; renamed so it is not confused with delivery instructions.
  if (name === 'style') return 'Variation';
  return name.replace(/^./, (first) => first.toUpperCase());
}

function settingValueLabel(name: OutputSettingName, value: number): string {
  if (name === 'speed') return `${value.toFixed(2)}x`;
  if (name === 'pitch') return `${value.toFixed(0)} st`;
  if (name === 'volume') return `${value.toFixed(1)} dB`;
  return value.toFixed(2);
}

function rangeMin(name: OutputSettingName): number {
  if (name === 'pitch') return -12;
  if (name === 'volume') return -12;
  if (name === 'speed') return 0.5;
  return 0;
}

function rangeMax(name: OutputSettingName): number {
  if (name === 'speed') return 2;
  if (name === 'pitch') return 12;
  if (name === 'volume') return 12;
  return 1;
}

function rangeStep(name: OutputSettingName): number {
  if (name === 'pitch') return 1;
  if (name === 'volume') return 0.5;
  return 0.01;
}

/** What each slider changes; the backend maps them per TTS engine (platform/voice/output_settings). */
function settingDescription(name: OutputSettingName): string {
  return {
    stability: 'Higher is steadier and more uniform; lower varies the delivery more (sampling temperature).',
    similarity: 'How closely the clone copies the sample. Below 0.50 Qwen uses only the voice timbre, not the delivery in the sample.',
    style: 'Higher allows more varied, expressive prosody (sampling variety).',
    speed: 'Speaking rate, without changing the pitch.',
    pitch: 'Voice pitch in semitones, without changing the speed.',
    volume: 'Output gain in dB on the whole take; a limiter keeps it below full scale.',
  }[name];
}
