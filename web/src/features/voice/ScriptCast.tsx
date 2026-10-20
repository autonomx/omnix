import { Button, Text } from '@mantine/core';
import type { VoiceScriptLine } from './api/voiceClient';
import { DELIVERY_SUGGESTIONS } from './audioEffects';
import type { ScriptSegmentRow, ScriptSpeakerRow } from './scriptLines';
import { voiceAssetId, voiceAssetName, voiceProfileName, voiceReference, type VoiceAsset } from './voiceAssets';

/**
 * Who says what: each detected speaker gets a library voice and, on engines that read them,
 * a delivery instruction. Below it, the script as the engine will hear it, with pauses.
 */
export function ScriptCast({
  speakers,
  segments,
  assets,
  voiceFor,
  deliveryFor,
  deliverySupported,
  engineLabel,
  onVoiceChange,
  onDeliveryChange,
  onPreview,
  savedLines,
  onRegenerateLine,
  onSelectTake,
  busyLineId = '',
}: {
  speakers: ScriptSpeakerRow[];
  segments: ScriptSegmentRow[];
  assets: VoiceAsset[];
  voiceFor: (speaker: ScriptSpeakerRow) => string;
  deliveryFor: (speaker: ScriptSpeakerRow) => string;
  deliverySupported: boolean;
  engineLabel: string;
  onVoiceChange: (speaker: string, voiceId: string) => void;
  onDeliveryChange: (speaker: string, instruction: string) => void;
  onPreview: (voiceId: string) => void;
  /** The open saved script's lines, aligned with ``segments``; absent while there are unsaved edits. */
  savedLines?: VoiceScriptLine[];
  onRegenerateLine?: (lineId: string) => void;
  onSelectTake?: (lineId: string, takeId: string) => void;
  busyLineId?: string;
}) {
  const deliveryReason = `${engineLabel || 'This engine'} does not read delivery instructions.`;
  return (
    <section className="voice-cast" aria-label="Cast">
      <div className="voice-cast-head">
        <b>Cast</b>
        <Text size="xs">{speakers.length} speaker{speakers.length === 1 ? '' : 's'} · {segments.length} line{segments.length === 1 ? '' : 's'}</Text>
      </div>
      <datalist id="voice-delivery-suggestions">
        {DELIVERY_SUGGESTIONS.map((suggestion) => <option key={suggestion} value={suggestion} />)}
      </datalist>
      <div className="voice-cast-rows">
        {speakers.map((speaker) => {
          const voiceValue = voiceFor(speaker);
          return (
            <div className="voice-cast-row" key={speaker.name}>
              <span className="voice-speaker-chip" title={`${speaker.count} line${speaker.count === 1 ? '' : 's'}`}>{speaker.name}</span>
              <select aria-label={`${speaker.name} voice`} value={voiceValue} onChange={(event) => onVoiceChange(speaker.name, event.currentTarget.value)}>
                {assets.map((asset) => <option key={voiceAssetId(asset)} value={voiceReference(asset)}>{voiceAssetName(asset)} ({voiceProfileName(asset)})</option>)}
                {!assets.length ? <option value="">No library voices</option> : null}
              </select>
              <input
                aria-label={`${speaker.name} delivery`}
                list="voice-delivery-suggestions"
                placeholder={deliverySupported ? 'Delivery (optional), e.g. Warm' : 'Delivery not supported'}
                title={deliverySupported ? 'A plain-language instruction the engine reads for this speaker.' : deliveryReason}
                disabled={!deliverySupported}
                value={deliverySupported ? deliveryFor(speaker) : ''}
                maxLength={200}
                onChange={(event) => onDeliveryChange(speaker.name, event.currentTarget.value)}
              />
              <Button aria-label={`Preview ${speaker.name} voice`} size="xs" variant="subtle" type="button" disabled={!voiceValue} onClick={() => onPreview(voiceValue)}>▶</Button>
            </div>
          );
        })}
      </div>
      {!deliverySupported ? <Text size="xs" className="voice-disabled-reason">{deliveryReason}</Text> : null}
      <ol className="voice-line-list" aria-label="Lines">
        {segments.map((segment, index) => {
          const line = savedLines?.[index];
          return (
            <li key={segment.index}>
              {segment.pause_before_ms ? <span className="voice-pause-marker">pause {segment.pause_before_ms} ms</span> : null}
              <span className="voice-speaker-chip">{segment.speaker}</span>
              <span className="voice-line-text">{segment.text}</span>
              {line ? (
                <span className="voice-line-takes">
                  {line.takes.length ? (
                    <select aria-label={`Line ${index + 1} take`} value={line.selected_take_id} onChange={(event) => onSelectTake?.(line.id, event.currentTarget.value)}>
                      {line.takes.map((take, takeIndex) => (
                        <option key={take.id} value={take.id}>Take {line.takes.length - takeIndex} · {take.duration.toFixed(1)} s{take.pinned ? ' ★' : ''}</option>
                      ))}
                    </select>
                  ) : <small>No take yet</small>}
                  <button type="button" aria-label={`Render line ${index + 1} again`} title="Render only this line again; the other lines keep their takes." disabled={busyLineId === line.id} onClick={() => onRegenerateLine?.(line.id)}>↻</button>
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
