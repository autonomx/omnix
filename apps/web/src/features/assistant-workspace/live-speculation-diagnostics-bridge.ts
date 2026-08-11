import { createLiveCallDiagnosticsReporter } from './live-call-diagnostics-client';

const PERF_EVENT = 'omnix:assistant-voice-perf';
const HOT_PATH_STAGE_PREFIXES = [
  'llm_speculation_',
  'tts_speculative_',
  'live_chat_direct_gateway_',
] as const;
const INSTALLED_KEY = '__omnixLiveSpeculationDiagnosticsInstalled';

type SpeculationDiagnosticsWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationDiagnosticsInstalled?: boolean;
};

export function isSpeculationDiagnosticStage(stage: string): boolean {
  return HOT_PATH_STAGE_PREFIXES.some((prefix) => stage.startsWith(prefix));
}

export function initializeLiveSpeculationDiagnosticsBridge(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as SpeculationDiagnosticsWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  const reporter = createLiveCallDiagnosticsReporter('live-call:speculation');

  const handlePerformance = (event: Event): void => {
    const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
    const stage = typeof detail.stage === 'string' ? detail.stage : '';
    if (!isSpeculationDiagnosticStage(stage)) return;
    const { stage: _stage, timestamp: _timestamp, ...safeDetails } = detail;
    reporter.record(stage, safeDetails, 'speculation');
  };

  window.addEventListener(PERF_EVENT, handlePerformance);
  return () => {
    window.removeEventListener(PERF_EVENT, handlePerformance);
    liveWindow[INSTALLED_KEY] = false;
    void reporter.close('speculation_diagnostics_stopped');
  };
}
