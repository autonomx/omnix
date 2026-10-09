/**
 * Omnix Scripts over HTTP (TVP-11.1–11.3): check a script, run it on a chart's bars on the server, the names the
 * editor completes, and a script's saved versions. Scripts themselves are trading documents (`tradingApi`, kind
 * `scripts`, payload {@link ScriptPayload}).
 */
import { unwrapLabelled } from '../../../api/http';
import type { components } from '../api/generated';
import { api } from '../api/gateway';

const scripts = <T>(call: Promise<{ data?: T; error?: unknown; response: Response }>) => unwrapLabelled(call, 'Omnix Scripts');

export type ScriptDiagnostic = components['schemas']['ScriptDiagnostic'];
export type ScriptCheckResult = components['schemas']['ScriptCheckResponse'];
export type ScriptReference = components['schemas']['ScriptReferenceResponse'];
export type ScriptVersionSummary = components['schemas']['ScriptVersionSummary'];
export type ScriptVersion = components['schemas']['ScriptVersion'];

/** A script document's payload. */
export type ScriptPayload = { name: string; source: string };

/** An input a script declares (`input.*`), as the server reports it. */
export type ScriptInput = { title: string; type: string; default: unknown; options?: Record<string, unknown> };
/** One `plot*`, `bgcolor`, `barcolor` or `alertcondition` call: a value per bar, and a colour per bar where it varies. */
export type ScriptPlot = {
  index: number;
  kind: string;
  title: string;
  options: Record<string, unknown>;
  values: unknown[];
  colors: unknown[] | null;
};
export type ScriptDrawing = { kind: string; id: number; fields: Record<string, unknown> };
/** A run's result (`scripts/worker.py` `result_payload`). */
export type ScriptRunResult = {
  declaration: { kind?: string; title?: string; shorttitle?: string; overlay?: boolean; precision?: number } & Record<string, unknown>;
  inputs: ScriptInput[];
  plots: ScriptPlot[];
  hlines: Array<{ price: unknown } & Record<string, unknown>>;
  fills: Array<Record<string, unknown>>;
  drawings: ScriptDrawing[];
  alerts: Array<Record<string, unknown>>;
  logs: Array<{ time: number | null; bar: number; level: string; message: string }>;
  profile: Array<{ line: number; seconds: number }>;
  bars: number;
  seconds: number;
};
export type ScriptRunResponse = { times: string[]; result: ScriptRunResult | null; error: ScriptDiagnostic | null };
export type ScriptRunRequest = {
  source: string;
  instrumentId: string;
  bindingId?: string | null;
  interval: string;
  inputs?: Record<string, unknown>;
  limit?: number;
  profile?: boolean;
};

export const scriptsApi = {
  check: (source: string): Promise<ScriptCheckResult> => scripts(api.POST('/api/trading/scripts/check', { body: { source } })),
  run: async (request: ScriptRunRequest): Promise<ScriptRunResponse> => {
    const response = await scripts(api.POST('/api/trading/scripts/run', {
      body: {
        source: request.source,
        instrument_id: request.instrumentId,
        binding_id: request.bindingId ?? null,
        interval: request.interval,
        inputs: request.inputs ?? {},
        limit: Math.max(10, Math.min(5_000, Math.round(request.limit ?? 1_000))),
        profile: request.profile ?? false,
      },
    }));
    return { times: response.times, result: (response.result ?? null) as ScriptRunResult | null, error: response.error ?? null };
  },
  reference: (): Promise<ScriptReference> => scripts(api.GET('/api/trading/scripts/reference')),
  versions: async (scriptId: string): Promise<ScriptVersionSummary[]> =>
    (await scripts(api.GET('/api/trading/scripts/{record_id}/versions', { params: { path: { record_id: scriptId } }, cache: 'no-store' }))).versions,
  version: (scriptId: string, revision: number): Promise<ScriptVersion> =>
    scripts(api.GET('/api/trading/scripts/{record_id}/versions/{revision}', { params: { path: { record_id: scriptId, revision } } })),
};
