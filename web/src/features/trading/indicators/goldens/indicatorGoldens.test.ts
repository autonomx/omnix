// @vitest-environment node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { CORE_INDICATOR_FORMULA_VERSION, indicatorOutputs, type CoreIndicatorId } from '../coreIndicators';
import {
  TRADINGVIEW_BUILTIN_DEFINITIONS,
  calculateTradingViewBuiltInOutputs,
  isTradingViewBuiltInId,
} from '../tradingViewBuiltIns';
import { GOLDEN_DATASETS, VARIANT_DATASET, asMarketBars, type GoldenDataset } from './goldenDatasets';

// Shared with the server registry tests (src/tests/trading/test_indicator_registry_goldens.py).
// Regenerate after an intended formula change: UPDATE_INDICATOR_GOLDENS=1 npm --prefix web run test -- indicatorGoldens
const GOLDEN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../resources/trading/indicator_goldens');
const UPDATE = process.env.UPDATE_INDICATOR_GOLDENS === '1';

type GoldenInputs = {
  period: number;
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  standardDeviations?: number;
};
type GoldenOutput = { key: string; points: Array<[number, number | null]> };
type GoldenCase = { case_id: string; dataset: string; inputs: GoldenInputs; error?: true; outputs: GoldenOutput[] };

function inputVariants(id: string, defaultPeriod: number): GoldenInputs[] {
  if (id === 'macd') {
    return [
      { period: defaultPeriod, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
      { period: defaultPeriod, fastPeriod: 8, slowPeriod: 21, signalPeriod: 5 },
    ];
  }
  if (id === 'bollinger') return [{ period: 20, standardDeviations: 2 }, { period: 10, standardDeviations: 1.5 }];
  const alternative = Math.max(2, Math.floor(defaultPeriod / 2) + 1);
  return alternative === defaultPeriod ? [{ period: defaultPeriod }] : [{ period: defaultPeriod }, { period: alternative }];
}

function computeOutputs(id: string, inputs: GoldenInputs, dataset: GoldenDataset): GoldenOutput[] {
  const bars = asMarketBars(dataset);
  const indexByTime = new Map(dataset.bars.map((bar, index) => [bar.start_time, index]));
  const outputs = isTradingViewBuiltInId(id)
    ? calculateTradingViewBuiltInOutputs(bars, { id, ...inputs })
    : indicatorOutputs(bars, { id: id as CoreIndicatorId, enabled: true, ...inputs });
  return outputs.map((output) => ({
    key: output.key,
    points: output.points.map((point): [number, number | null] => {
      const index = indexByTime.get(point.time);
      if (index === undefined) throw new Error(`${id} produced a point at ${point.time}, which is not a bar start`);
      return [index, Number.isFinite(point.value) ? point.value : null];
    }),
  }));
}

function goldenCase(id: string, caseId: string, inputs: GoldenInputs, dataset: GoldenDataset): GoldenCase {
  try {
    return { case_id: caseId, dataset: dataset.name, inputs, outputs: computeOutputs(id, inputs, dataset) };
  } catch {
    return { case_id: caseId, dataset: dataset.name, inputs, error: true, outputs: [] };
  }
}

function indicatorFile(id: string, name: string, defaultPeriod: number): string {
  const [defaults, ...others] = inputVariants(id, defaultPeriod);
  const cases = GOLDEN_DATASETS.map((dataset) => goldenCase(id, `${dataset.name}/default`, defaults, dataset));
  const variantDataset = GOLDEN_DATASETS.find((dataset) => dataset.name === VARIANT_DATASET)!;
  others.forEach((inputs, index) => cases.push(goldenCase(id, `${VARIANT_DATASET}/variant-${index + 1}`, inputs, variantDataset)));
  const header = JSON.stringify({ formula_version: CORE_INDICATOR_FORMULA_VERSION, id, name });
  return `${header.slice(0, -1)},"cases":[\n${cases.map((item) => JSON.stringify(item)).join(',\n')}\n]}\n`;
}

function datasetFile(dataset: GoldenDataset): string {
  return `{"name":${JSON.stringify(dataset.name)},"bars":[\n${dataset.bars.map((item) => JSON.stringify(item)).join(',\n')}\n]}\n`;
}

const AVAILABLE = TRADINGVIEW_BUILTIN_DEFINITIONS.filter((definition) => definition.available);

function expectFile(path: string, content: string): void {
  if (UPDATE) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
    return;
  }
  expect(existsSync(path), `${path} is missing; regenerate with UPDATE_INDICATOR_GOLDENS=1`).toBe(true);
  expect(readFileSync(path, 'utf8').replace(/\r\n/g, '\n')).toBe(content);
}

describe('indicator goldens shared with the server registry', () => {
  it('covers every available built-in indicator', () => {
    expect(AVAILABLE.length).toBeGreaterThanOrEqual(100);
    expectFile(join(GOLDEN_ROOT, 'index.json'), `${JSON.stringify({
      formula_version: CORE_INDICATOR_FORMULA_VERSION,
      datasets: GOLDEN_DATASETS.map((dataset) => dataset.name),
      indicators: AVAILABLE.map(({ id, name }) => ({ id, name })),
    }, null, 1)}\n`);
  });

  it.each(GOLDEN_DATASETS.map((dataset) => [dataset.name, dataset] as const))('dataset %s is current', (name, dataset) => {
    expectFile(join(GOLDEN_ROOT, 'datasets', `${name}.json`), datasetFile(dataset));
  });

  it.each(AVAILABLE.map((definition) => [definition.id, definition] as const))('%s matches its golden file', (id, definition) => {
    expectFile(join(GOLDEN_ROOT, 'indicators', `${id}.json`), indicatorFile(id, definition.name, definition.defaultPeriod));
  });
});
