/**
 * Omnix Scripts on the chart (TVP-11.1): a saved script added to a chart is the indicator `script-<record id>`. Its
 * outputs come from a run on the server (`/api/trading/scripts/run`, the latest bars of the chart's symbol and
 * interval), mapped onto the chart's bars by time:
 *
 * - `plot` is a line or histogram (circles and crosses are markers), with its colour per bar;
 * - `plotshape`, `plotchar` and `plotarrow` are markers above or below the bar (at the value with `location.absolute`);
 * - `bgcolor` shades the price pane and `barcolor` recolours the bars;
 * - `hline` is a level; `line.new` and `box.new` drawings are lines, `label.new` a marker with its text;
 * - `fill`, `plotcandle`, `plotbar` and `table` are not drawn yet (the console says so).
 *
 * An instance keeps the script's name, whether it overlays the price, the revision it last ran and its input values
 * (`params`, inputs as `in:<title>`), so a layout can show it before the script loads.
 */
import type { CoreIndicatorId, CoreIndicatorInstance, IndicatorOutput, IndicatorPoint } from '../indicators/coreIndicators';
import type { MarketBar } from '../tradingTypes';
import { tradingApi } from '../tradingApi';
import { scriptsApi, type ScriptPayload, type ScriptPlot, type ScriptRunResponse, type ScriptRunResult } from './scriptsApi';

export const SCRIPT_INDICATOR_PREFIX = 'script-';
const INPUT_PREFIX = 'in:';
/** Lines and boxes drawn per script; more are listed in the console as not drawn. */
export const MAX_SCRIPT_DRAWINGS = 50;

export function isScriptIndicatorId(id: string): boolean {
  return id.startsWith(SCRIPT_INDICATOR_PREFIX) && id.length > SCRIPT_INDICATOR_PREFIX.length;
}

/** The script document a script indicator runs, or null for another indicator. */
export function scriptIdOf(id: string): string | null {
  return isScriptIndicatorId(id) ? id.slice(SCRIPT_INDICATOR_PREFIX.length) : null;
}

/** A new script record id: no colon, so its indicator's output keys split on the first one (`chartAdapter`). */
export function newScriptRecordId(): string {
  return `s${crypto.randomUUID().replace(/-/g, '')}`;
}

export function scriptIndicatorInstance(scriptId: string, name: string, overlay: boolean, revision: number): CoreIndicatorInstance {
  return {
    id: `${SCRIPT_INDICATOR_PREFIX}${scriptId}` as CoreIndicatorId,
    period: 1,
    enabled: true,
    visible: true,
    params: { name, overlay: overlay ? 1 : 0, revision },
  };
}

/** The name a script indicator shows (legend, settings), or null for another indicator. */
export function scriptIndicatorName(indicator: Pick<CoreIndicatorInstance, 'id' | 'params'>): string | null {
  if (!isScriptIndicatorId(String(indicator.id))) return null;
  const name = indicator.params?.name;
  return typeof name === 'string' && name ? name : 'Script';
}

/** The input values an instance sets, by input title (`in:<title>` params). */
export function scriptInputValues(indicator: Pick<CoreIndicatorInstance, 'params'>): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(indicator.params ?? {})) {
    if (!key.startsWith(INPUT_PREFIX)) continue;
    values[key.slice(INPUT_PREFIX.length)] = value === 'true' ? true : value === 'false' ? false : value;
  }
  return values;
}

/** Params with an input set (booleans kept as 'true'/'false', since params hold numbers and strings). */
export function withScriptInput(params: CoreIndicatorInstance['params'], title: string, value: unknown): Record<string, number | string> {
  const stored = typeof value === 'boolean' ? String(value) : typeof value === 'number' && Number.isFinite(value) ? value : String(value ?? '');
  return { ...(params ?? {}), [`${INPUT_PREFIX}${title}`]: stored };
}

/** `#RRGGBBAA` (Pine colours with transparency) as `rgba()`; other colours as they are; null for na. */
export function scriptColor(value: unknown): string | null {
  const raw = value && typeof value === 'object' && 'color' in value ? (value as { color: unknown }).color : value;
  if (typeof raw !== 'string' || !raw) return null;
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(raw);
  if (!match) return raw;
  const [r, g, b, a] = match.slice(1).map((part) => Number.parseInt(part, 16));
  return `rgba(${r}, ${g}, ${b}, ${Number((a / 255).toFixed(3))})`;
}

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

type Mapped = { outputs: IndicatorOutput[]; notDrawn: string[] };
type ChartBars = { times: (string | undefined)[]; closes: number[]; highs: number[]; lows: number[]; chartTimes: string[] };

/** The run's bars as chart times: index i of the run is chart bar `times[i]` (undefined when the chart lacks it). */
function alignBars(runTimes: readonly string[], bars: readonly MarketBar[]): ChartBars {
  const byTime = new Map(bars.map((bar, index) => [Date.parse(bar.start_time), index]));
  const indexes = runTimes.map((time) => byTime.get(Date.parse(time)));
  return {
    times: indexes.map((index) => (index === undefined ? undefined : bars[index].start_time)),
    closes: indexes.map((index) => (index === undefined ? Number.NaN : Number(bars[index].close))),
    highs: indexes.map((index) => (index === undefined ? Number.NaN : Number(bars[index].high))),
    lows: indexes.map((index) => (index === undefined ? Number.NaN : Number(bars[index].low))),
    chartTimes: bars.map((bar) => bar.start_time),
  };
}

const LINE_STYLES: Record<string, IndicatorOutput['lineStyle']> = {
  'hline.style_dashed': 'dashed', 'hline.style_dotted': 'dotted', 'hline.style_solid': 'solid',
  'line.style_dashed': 'dashed', 'line.style_dotted': 'dotted', 'line.style_solid': 'solid',
};

function markerShape(style: unknown, fallback: IndicatorOutput['marker']): IndicatorOutput['marker'] {
  const name = String(style ?? '');
  if (/up$/.test(name)) return 'arrowUp';
  if (/down$/.test(name)) return 'arrowDown';
  return name ? 'circle' : fallback;
}

/** A run's result as chart outputs, on the chart's bars. */
export function scriptOutputs(indicator: CoreIndicatorInstance, result: ScriptRunResult, runTimes: readonly string[], bars: readonly MarketBar[]): Mapped {
  const id = String(indicator.id);
  const aligned = alignBars(runTimes, bars);
  const overlay = result.declaration.overlay === true;
  const ownPane: 0 | 1 = overlay ? 0 : 1;
  const precision = finite(result.declaration.precision) ? result.declaration.precision : null;
  const notDrawn: string[] = [];
  const outputs: IndicatorOutput[] = [];
  const style = indicator.style;
  const add = (output: Omit<IndicatorOutput, 'visible' | 'precision'>) => {
    if (output.points.length === 0 && output.kind !== 'viewport-average') return;
    outputs.push({
      ...output,
      visible: style?.plots?.[output.key] !== false,
      color: style?.colors?.[output.key] ?? output.color,
      lineStyle: style?.lineStyles?.[output.key] ?? output.lineStyle,
      lineWidth: style?.lineWidth ?? output.lineWidth,
      precision: style?.precision ?? precision,
      labelsOnPriceScale: style?.labelsOnPriceScale ?? output.labelsOnPriceScale ?? true,
      valuesInStatusLine: style?.valuesInStatusLine ?? true,
      inputsInStatusLine: false,
    });
  };
  for (const plot of result.plots) mapPlot(id, plot, aligned, ownPane, add, notDrawn);
  result.hlines.forEach((hline, index) => {
    const price = Number(hline.price);
    if (!Number.isFinite(price)) return;
    add({
      key: `${id}:hline${index}`, title: String(hline.title ?? `Level ${price}`), pane: ownPane, kind: 'line', render: 'levels',
      points: aligned.chartTimes.map((time) => ({ time, value: price })),
      color: scriptColor(hline.color) ?? '#787b86', lineStyle: LINE_STYLES[String(hline.linestyle ?? 'hline.style_dashed')] ?? 'dashed', lineWidth: 1,
    });
  });
  if (result.fills.length > 0) notDrawn.push(`fill() ×${result.fills.length}`);
  mapDrawings(id, result, aligned, ownPane, add, notDrawn);
  return { outputs: outputs.filter((output) => output.visible !== false), notDrawn };
}

function mapPlot(
  id: string, plot: ScriptPlot, bars: ChartBars, ownPane: 0 | 1, add: (output: Omit<IndicatorOutput, 'visible' | 'precision'>) => void, notDrawn: string[],
): void {
  const key = `${id}:p${plot.index}`;
  const options = plot.options ?? {};
  const colorAt = (index: number): string | null => scriptColor(plot.colors?.[index]) ?? scriptColor(options.color);
  const pane: 0 | 1 = options.force_overlay === true ? 0 : ownPane;
  if (plot.kind === 'plot') {
    const plotStyle = String(options.style ?? 'plot.style_line');
    const points: IndicatorPoint[] = [];
    plot.values.forEach((value, index) => {
      const time = bars.times[index];
      const color = plot.colors ? colorAt(index) : null;
      // An na colour hides that bar's value, as in Pine.
      if (!time || !finite(value) || (plot.colors && color === null)) return;
      points.push({ time, value, ...(color ? { color } : {}) });
    });
    const histogram = plotStyle === 'plot.style_histogram' || plotStyle === 'plot.style_columns';
    const markers = plotStyle === 'plot.style_circles' || plotStyle === 'plot.style_cross';
    const width = Math.min(4, Math.max(1, Math.round(Number(options.linewidth ?? 1)))) as 1 | 2 | 3 | 4;
    add({
      key, title: plot.title, pane, kind: histogram ? 'histogram' : 'line', points, color: colorAt(0) ?? '#2962ff', lineWidth: width,
      ...(markers ? { render: 'markers' as const, marker: 'circle' as const } : plotStyle.endsWith('br') ? { render: 'levels' as const } : {}),
    });
    return;
  }
  if (plot.kind === 'plotshape' || plot.kind === 'plotchar' || plot.kind === 'plotarrow') {
    mapMarkers(key, plot, bars, pane, colorAt, add);
    return;
  }
  if (plot.kind === 'bgcolor' || plot.kind === 'barcolor') {
    const points: IndicatorPoint[] = [];
    plot.values.forEach((value, index) => {
      const time = bars.times[index];
      const color = scriptColor(value);
      if (time && color) points.push({ time, value: 1, color });
    });
    add({ key, title: plot.title, pane: 0, kind: plot.kind === 'bgcolor' ? 'background' : 'bar-colors', points, labelsOnPriceScale: false });
    return;
  }
  if (plot.kind !== 'alertcondition') notDrawn.push(`${plot.kind}() "${plot.title}"`);
}

function mapMarkers(
  key: string, plot: ScriptPlot, bars: ChartBars, pane: 0 | 1, colorAt: (index: number) => string | null,
  add: (output: Omit<IndicatorOutput, 'visible' | 'precision'>) => void,
): void {
  const options = plot.options ?? {};
  if (plot.kind === 'plotarrow') {
    const up: IndicatorPoint[] = [];
    const down: IndicatorPoint[] = [];
    plot.values.forEach((value, index) => {
      const time = bars.times[index];
      if (!time || !finite(value) || value === 0) return;
      (value > 0 ? up : down).push({ time, value: value > 0 ? bars.lows[index] : bars.highs[index] });
    });
    add({ key: `${key}:up`, title: `${plot.title} up`, pane: 0, kind: 'line', render: 'markers', marker: 'arrowUp', markerPosition: 'belowBar', points: up, color: scriptColor(options.colorup) ?? '#089981' });
    add({ key: `${key}:down`, title: `${plot.title} down`, pane: 0, kind: 'line', render: 'markers', marker: 'arrowDown', markerPosition: 'aboveBar', points: down, color: scriptColor(options.colordown) ?? '#f23645' });
    return;
  }
  const location = String(options.location ?? 'location.abovebar');
  const absolute = location === 'location.absolute';
  const points: IndicatorPoint[] = [];
  plot.values.forEach((value, index) => {
    const time = bars.times[index];
    if (!time || !(value === true || finite(value))) return;
    const color = plot.colors ? colorAt(index) : null;
    points.push({ time, value: absolute && finite(value) ? value : bars.closes[index], ...(color ? { color } : {}) });
  });
  const text = String(options.text ?? (plot.kind === 'plotchar' ? options.char ?? '★' : '') ?? '');
  const position = absolute ? undefined : location === 'location.belowbar' || location === 'location.bottom' ? 'belowBar' as const : 'aboveBar' as const;
  const fallbackShape = position === 'belowBar' ? 'arrowUp' : position === 'aboveBar' ? 'arrowDown' : 'circle';
  add({
    key, title: plot.title, pane: absolute ? pane : 0, kind: 'line', render: 'markers', points, color: colorAt(0) ?? '#2962ff',
    marker: plot.kind === 'plotchar' ? 'circle' : markerShape(options.style, fallbackShape),
    ...(position ? { markerPosition: position } : {}), ...(text ? { markerText: text } : {}),
  });
}

function mapDrawings(
  id: string, result: ScriptRunResult, bars: ChartBars, ownPane: 0 | 1, add: (output: Omit<IndicatorOutput, 'visible' | 'precision'>) => void, notDrawn: string[],
): void {
  const timeAt = (x: unknown, xloc: unknown): string | undefined => {
    if (!finite(x)) return undefined;
    if (xloc === 'xloc.bar_time') {
      const index = bars.chartTimes.findIndex((time) => Date.parse(time) === x);
      return index < 0 ? undefined : bars.chartTimes[index];
    }
    return bars.times[Math.round(x)];
  };
  const labels: IndicatorPoint[] = [];
  let drawn = 0;
  let skipped = 0;
  let tables = 0;
  for (const drawing of result.drawings) {
    const fields = drawing.fields;
    const pane: 0 | 1 = fields.force_overlay === true ? 0 : ownPane;
    if (drawing.kind === 'label') {
      const time = timeAt(fields.x, fields.xloc);
      if (time && finite(fields.y)) labels.push({ time, value: fields.y, label: String(fields.text ?? ''), color: scriptColor(fields.color) ?? '#2962ff' });
      continue;
    }
    if (drawing.kind === 'table') { tables += 1; continue; }
    if (drawing.kind !== 'line' && drawing.kind !== 'box') continue;
    if (drawn >= MAX_SCRIPT_DRAWINGS) { skipped += 1; continue; }
    const line = drawing.kind === 'line';
    const from = timeAt(line ? fields.x1 : fields.left, fields.xloc);
    const to = timeAt(line ? fields.x2 : fields.right, fields.xloc);
    const a = Number(line ? fields.y1 : fields.top);
    const b = Number(line ? fields.y2 : fields.bottom);
    if (!from || !to || from === to || !Number.isFinite(a) || !Number.isFinite(b)) continue;
    const [start, end, startValue, endValue] = Date.parse(from) < Date.parse(to) ? [from, to, a, b] : [to, from, b, a];
    const color = scriptColor(line ? fields.color : fields.border_color) ?? '#2962ff';
    const lineStyle = LINE_STYLES[String(fields.style ?? fields.border_style ?? '')] ?? 'solid';
    const base = { pane, kind: 'line' as const, color, lineStyle, lineWidth: 1 as const, labelsOnPriceScale: false };
    drawn += 1;
    if (line) {
      add({ ...base, key: `${id}:d${drawing.id}`, title: `line ${drawing.id}`, points: [{ time: start, value: startValue }, { time: end, value: endValue }] });
    } else {
      add({ ...base, key: `${id}:d${drawing.id}:top`, title: `box ${drawing.id}`, points: [{ time: start, value: a }, { time: end, value: a }] });
      add({ ...base, key: `${id}:d${drawing.id}:bottom`, title: `box ${drawing.id}`, points: [{ time: start, value: b }, { time: end, value: b }] });
    }
  }
  if (labels.length > 0) add({ key: `${id}:labels`, title: 'Labels', pane: ownPane, kind: 'line', render: 'markers', marker: 'circle', points: labels, labelsOnPriceScale: false });
  if (skipped > 0) notDrawn.push(`${skipped} lines and boxes beyond ${MAX_SCRIPT_DRAWINGS}`);
  if (tables > 0) notDrawn.push(`table ×${tables}`);
}

// --- Running scripts for the chart -----------------------------------------------------------------------------------

/** What a chart's last run of a script reported, for the editor's console. */
export type ScriptRunStatus = { at: number; error: string | null; logs: ScriptRunResult['logs']; notDrawn: string[] };
const statuses = new Map<string, ScriptRunStatus>();
const statusListeners = new Set<() => void>();

export function scriptRunStatus(scriptId: string): ScriptRunStatus | null {
  return statuses.get(scriptId) ?? null;
}

export function subscribeScriptRunStatus(listener: () => void): () => void {
  statusListeners.add(listener);
  return () => statusListeners.delete(listener);
}

function recordStatus(scriptId: string, status: ScriptRunStatus): void {
  statuses.set(scriptId, status);
  for (const listener of statusListeners) listener();
}

type SourceEntry = { revision: number; at: number; source: Promise<ScriptPayload & { revision: number }> };
const sources = new Map<string, SourceEntry>();
/** How long a loaded script is used before it is read again (a save in another tab). */
const SOURCE_TTL_MS = 60_000;

/** A script's saved source: at least `revision` (an instance's last known one), and at most a minute old. */
export function loadScriptSource(scriptId: string, revision = 0): Promise<ScriptPayload & { revision: number }> {
  const cached = sources.get(scriptId);
  if (cached && cached.revision >= revision && Date.now() - cached.at < SOURCE_TTL_MS) return cached.source;
  const source = tradingApi.document('scripts', scriptId).then((record) => ({
    name: String(record.payload.name ?? ''), source: String(record.payload.source ?? ''), revision: record.revision,
  }));
  sources.set(scriptId, { revision, at: Date.now(), source });
  source.then((loaded) => sources.set(scriptId, { revision: loaded.revision, at: Date.now(), source }), () => sources.delete(scriptId));
  return source;
}

/** Forget a script's source (the editor saved it). */
export function forgetScriptSource(scriptId: string): void {
  sources.delete(scriptId);
}

const runs = new Map<string, { at: number; run: Promise<ScriptRunResponse> }>();
const MAX_CACHED_RUNS = 32;
/** A forming bar's ticks re-run a script at most this often (each run is a server request and a worker run). */
export const SCRIPT_LIVE_RERUN_MS = 5_000;

/**
 * One run per script, inputs and bars, shared by every chart showing them. Ticks of the same forming bar reuse the
 * last run for SCRIPT_LIVE_RERUN_MS; a new bar runs at once.
 */
function runOnce(key: string, tick: string, run: () => Promise<ScriptRunResponse>, now = Date.now()): Promise<ScriptRunResponse> {
  const exact = runs.get(`${key}|${tick}`);
  if (exact) return exact.run;
  const recent = runs.get(key);
  if (recent && now - recent.at < SCRIPT_LIVE_RERUN_MS) return recent.run;
  const started = run();
  const entry = { at: now, run: started };
  runs.set(key, entry);
  runs.set(`${key}|${tick}`, entry);
  started.catch(() => { runs.delete(key); runs.delete(`${key}|${tick}`); });
  while (runs.size > MAX_CACHED_RUNS) runs.delete(runs.keys().next().value as string);
  return started;
}

export type ScriptIndicatorContext = { bindingId?: string | null };

/** A script indicator's outputs on the chart's bars; none while the script can't load or run (the console says why). */
export async function calculateScriptIndicatorOutputs(
  bars: readonly MarketBar[], indicator: CoreIndicatorInstance, context: ScriptIndicatorContext = {},
): Promise<IndicatorOutput[]> {
  const scriptId = scriptIdOf(String(indicator.id));
  const first = bars[0];
  const last = bars.at(-1);
  if (!scriptId || !first || !last) return [];
  try {
    const script = await loadScriptSource(scriptId, Number(indicator.params?.revision ?? 0));
    const inputs = scriptInputValues(indicator);
    const request = {
      source: script.source, instrumentId: first.instrument_id, bindingId: context.bindingId ?? null, interval: first.interval, inputs, limit: bars.length,
    };
    const key = JSON.stringify([scriptId, script.revision, request.instrumentId, request.bindingId, request.interval, inputs, bars.length, last.start_time]);
    const response = await runOnce(key, `${last.close}|${last.high}|${last.low}|${last.volume}|${last.is_final}`, () => scriptsApi.run(request));
    if (!response.result) {
      const error = response.error;
      recordStatus(scriptId, { at: Date.now(), error: error ? `${error.line ? `line ${error.line}: ` : ''}${error.message}` : 'The script did not run.', logs: [], notDrawn: [] });
      return [];
    }
    const mapped = scriptOutputs(indicator, response.result, response.times, bars);
    recordStatus(scriptId, { at: Date.now(), error: null, logs: response.result.logs, notDrawn: mapped.notDrawn });
    return mapped.outputs;
  } catch (error) {
    recordStatus(scriptId, { at: Date.now(), error: error instanceof Error ? error.message : String(error), logs: [], notDrawn: [] });
    return [];
  }
}
