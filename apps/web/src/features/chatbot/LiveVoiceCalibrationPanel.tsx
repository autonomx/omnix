import { useEffect, useState } from 'react';

import {
  LIVE_VOICE_CALIBRATION_UPDATED_EVENT,
  readLatestLiveVoiceCalibration,
  resolveCalibrationDuplex,
  runBrowserLiveVoiceCalibration,
  type LiveVoiceCalibrationRecord,
} from '../assistant-workspace/live-voice-calibration';

export function LiveVoiceCalibrationPanel() {
  const [record, setRecord] = useState<LiveVoiceCalibrationRecord | null>(() => readLatestLiveVoiceCalibration());
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const handle = (event: Event) => {
      setRecord((event as CustomEvent<LiveVoiceCalibrationRecord>).detail ?? readLatestLiveVoiceCalibration());
    };
    window.addEventListener(LIVE_VOICE_CALIBRATION_UPDATED_EVENT, handle);
    return () => window.removeEventListener(LIVE_VOICE_CALIBRATION_UPDATED_EVENT, handle);
  }, []);

  async function calibrate(): Promise<void> {
    if (running) return;
    setRunning(true);
    setStatus('Measuring room noise…');
    try {
      const next = await runBrowserLiveVoiceCalibration((stage) => {
        if (stage === 'noise') setStatus('Stay quiet while room noise is measured…');
        if (stage === 'echo') setStatus('Playing a short calibration tone…');
        if (stage === 'speech') setStatus('Say “testing one two” in your normal voice…');
        if (stage === 'complete') setStatus('Calibration complete.');
      });
      setRecord(next);
      setStatus(next.resolvedMode === 'echo_aware'
        ? 'Automatic mode can use echo-aware barge-in for this device pair.'
        : `Automatic mode will stay safe half-duplex: ${humanReason(next.reason)}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Calibration could not be completed.');
    } finally {
      setRunning(false);
    }
  }

  const resolution = resolveCalibrationDuplex(record);
  const confidence = Math.round((record?.confidence ?? 0) * 100);
  return (
    <section className="live-chat-card" aria-labelledby="live-chat-calibration-heading">
      <header>
        <div>
          <p className="eyebrow">Duplex calibration</p>
          <h3 id="live-chat-calibration-heading">Microphone and speakers</h3>
          <p>Automatic mode uses a short local calibration before enabling echo-aware barge-in.</p>
        </div>
        <button type="button" disabled={running} onClick={() => void calibrate()}>
          {running ? 'Calibrating…' : record ? 'Re-run calibration' : 'Calibrate microphone and speakers'}
        </button>
      </header>
      <dl className="live-chat-metrics live-chat-calibration-metrics">
        <div><dt>Resolved mode</dt><dd>{resolution.mode === 'echo_aware' ? 'Echo-aware' : 'Safe half-duplex'}</dd></div>
        <div><dt>Confidence</dt><dd>{confidence}%</dd></div>
        <div><dt>Status</dt><dd>{record ? humanReason(resolution.reason) : 'Not calibrated'}</dd></div>
        <div><dt>Last calibration</dt><dd>{record ? new Date(record.createdAt).toLocaleString() : 'Never'}</dd></div>
      </dl>
      <p className="live-chat-note">Calibration stores only numeric environment measurements and a device-pair hash. It does not retain conversation audio or transcript text.</p>
      {status ? <p className="live-chat-note" role="status">{status}</p> : null}
    </section>
  );
}

function humanReason(reason: string): string {
  return reason.replaceAll('_', ' ').replace(/^./, (value) => value.toLocaleUpperCase());
}
