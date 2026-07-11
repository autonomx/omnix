import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const calibration = {
  version: 'live-voice-calibration-v1' as const,
  deviceKey: 'device-pair',
  createdAt: 1_000,
  expiresAt: Date.now() + 60_000,
  noiseFloorRms: 0.002,
  playbackRms: 0.04,
  echoGain: 0.2,
  delayMs: 40,
  similarity: 0.9,
  userSpeechSeparation: 2.2,
  confidence: 0.91,
  resolvedMode: 'echo_aware' as const,
  reason: 'calibration_confident',
};

const runCalibration = vi.fn();

vi.mock('../assistant-workspace/live-voice-calibration', () => ({
  LIVE_VOICE_CALIBRATION_UPDATED_EVENT: 'omnix:live-voice-calibration-updated',
  readLatestLiveVoiceCalibration: () => null,
  resolveCalibrationDuplex: (record: typeof calibration | null) => record
    ? { mode: record.resolvedMode, confidence: record.confidence, reason: record.reason }
    : { mode: 'half_duplex', confidence: 0, reason: 'calibration_missing' },
  runBrowserLiveVoiceCalibration: (...args: unknown[]) => runCalibration(...args),
}));

import { LiveVoiceCalibrationPanel } from './LiveVoiceCalibrationPanel';

describe('LiveVoiceCalibrationPanel', () => {
  beforeEach(() => runCalibration.mockReset());

  it('shows safe fallback before calibration', () => {
    render(<LiveVoiceCalibrationPanel />);
    expect(screen.getByRole('button', { name: 'Calibrate microphone and speakers' })).toBeInTheDocument();
    expect(screen.getByText('Safe half-duplex')).toBeInTheDocument();
    expect(screen.getByText('Not calibrated')).toBeInTheDocument();
  });

  it('runs calibration and displays the evidence-backed mode', async () => {
    runCalibration.mockImplementation(async (onStage?: (stage: string) => void) => {
      onStage?.('noise');
      onStage?.('echo');
      onStage?.('speech');
      onStage?.('complete');
      return calibration;
    });
    render(<LiveVoiceCalibrationPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Calibrate microphone and speakers' }));

    expect(await screen.findByText('Echo-aware')).toBeInTheDocument();
    expect(screen.getByText('91%')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Automatic mode can use echo-aware barge-in');
  });
});
