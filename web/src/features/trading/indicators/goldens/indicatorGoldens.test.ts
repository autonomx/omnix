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
  tradingViewBuiltInUsesCompareSeries,
} from '../tradingViewBuiltIns';
import {
  ALTERNATIVE_PERIOD_DATASET,
  COMPARE_DATASET,
  COMPARE_SYMBOL,
  INPUT_VARIANT_DATASET,
  asMarketBars,
  generateCompareDatasets,
  generateGoldenDatasets,
  type GoldenDataset,
} from './goldenDatasets';

// Shared with the server registry tests (src/tests/trading/test_indicator_registry_goldens.py).
// Regenerate after an intended formula change: UPDATE_INDICATOR_GOLDENS=1 npm --prefix web run test -- indicatorGoldens
const GOLDEN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../resources/trading/indicator_goldens');
const UPDATE = process.env.UPDATE_INDICATOR_GOLDENS === '1';
const DATASET_NAMES = generateGoldenDatasets().map((dataset) => dataset.name);
// Second series for compare-symbol indicators only, so adding them leaves every other golden file unchanged.
const COMPARE_DATASET_NAMES = generateCompareDatasets().map((dataset) => dataset.name);

type GoldenInputs = {
  period: number;
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  standardDeviations?: number;
  anchorTime?: string;
  compareSymbol?: string;
};
type GoldenOutput = { key: string; points: Array<[number, number | null]> };
type GoldenCase = { case_id: string; dataset: string; compare_dataset?: string; inputs: GoldenInputs; error?: true; outputs: GoldenOutput[] };

// The engines' own input validation; any other exception is a bug and must fail the run.
const VALIDATION_ERROR = /must be a positive integer|must be positive|must be smaller than/;

function datasetPath(name: string): string {
  return join(GOLDEN_ROOT, 'datasets', `${name}.json`);
}

function loadDatasets(names: readonly string[], generate: () => GoldenDataset[]): GoldenDataset[] {
  if (UPDATE) return generate();
  return names.map((name) => JSON.parse(readFileSync(datasetPath(name), 'utf8')) as GoldenDataset);
}

const DATASETS = loadDatasets(DATASET_NAMES, generateGoldenDatasets);
const COMPARE_DATASETS = loadDatasets(COMPARE_DATASET_NAMES, generateCompareDatasets);
const datasetByName = new Map([...DATASETS, ...COMPARE_DATASETS].map((dataset) => [dataset.name, dataset]));

function alternativePeriods(id: string, defaultPeriod: number): GoldenInputs[] {
  if (id === 'macd') return [{ period: defaultPeriod, fastPeriod: 8, slowPeriod: 21, signalPeriod: 5 }];
  if (id === 'bollinger') return [{ period: 10, standardDeviations: 1.5 }];
  const alternative = Math.max(2, Math.floor(defaultPeriod / 2) + 1);
  return alternative === defaultPeriod ? [] : [{ period: alternative }];
}

function defaultInputs(id: string, defaultPeriod: number): GoldenInputs {
  if (id === 'macd') return { period: defaultPeriod, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 };
  if (id === 'bollinger') return { period: 20, standardDeviations: 2 };
  return { period: defaultPeriod };
}

function inputVariants(id: string, defaultPeriod: number): Array<[string, GoldenInputs]> {
  const variants: Array<[string, GoldenInputs]> = [
    ['inputs', { period: defaultPeriod, fastPeriod: 7, slowPeriod: 30, signalPeriod: 4, standardDeviations: 1.5 }],
    ['fast-above-slow', { period: 4, fastPeriod: 9, slowPeriod: 5, signalPeriod: 3 }],
    ['fractional-period', { period: 2.5 }],
    ['zero-period', { period: 0 }],
    ['zero-deviation', { period: defaultPeriod, standardDeviations: 0 }],
  ];
  if (id === 'vwap') {
    const anchor = datasetByName.get(INPUT_VARIANT_DATASET)!.bars[37].start_time;
    variants.push(['anchored', { period: defaultPeriod, anchorTime: anchor }], ['anchored-after-last-bar', { period: defaultPeriod, anchorTime: '2030-01-01T00:00:00Z' }]);
  }
  return variants;
}

function computeOutputs(id: string, inputs: GoldenInputs, dataset: GoldenDataset, compare?: GoldenDataset): GoldenOutput[] {
  const bars = asMarketBars(dataset);
  const indexByTime = new Map(dataset.bars.map((bar, index) => [bar.start_time, index]));
  const outputs = isTradingViewBuiltInId(id)
    ? calculateTradingViewBuiltInOutputs(bars, { id, ...inputs }, { compareBars: compare ? asMarketBars(compare) : undefined })
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
  // Compare-symbol indicators read the compare dataset as the second series whenever the inputs name a symbol.
  const compare = inputs.compareSymbol ? datasetByName.get(COMPARE_DATASET)! : undefined;
  const series = compare ? { dataset: dataset.name, compare_dataset: compare.name } : { dataset: dataset.name };
  try {
    return { case_id: caseId, ...series, inputs, outputs: computeOutputs(id, inputs, dataset, compare) };
  } catch (error) {
    if (!(error instanceof Error) || !VALIDATION_ERROR.test(error.message)) throw error;
    return { case_id: caseId, ...series, inputs, error: true, outputs: [] };
  }
}

function indicatorFile(id: string, name: string, defaultPeriod: number): string {
  const usesCompare = tradingViewBuiltInUsesCompareSeries(id);
  const withCompare = (inputs: GoldenInputs): GoldenInputs => (usesCompare ? { ...inputs, compareSymbol: COMPARE_SYMBOL } : inputs);
  const defaults = withCompare(defaultInputs(id, defaultPeriod));
  const cases = DATASETS.map((dataset) => goldenCase(id, `${dataset.name}/default`, defaults, dataset));
  const alternativeDataset = datasetByName.get(ALTERNATIVE_PERIOD_DATASET)!;
  alternativePeriods(id, defaultPeriod).forEach((inputs, index) => {
    cases.push(goldenCase(id, `${ALTERNATIVE_PERIOD_DATASET}/variant-${index + 1}`, withCompare(inputs), alternativeDataset));
  });
  const variantDataset = datasetByName.get(INPUT_VARIANT_DATASET)!;
  inputVariants(id, defaultPeriod).forEach(([label, inputs]) => {
    cases.push(goldenCase(id, `${INPUT_VARIANT_DATASET}/${label}`, withCompare(inputs), variantDataset));
  });
  if (usesCompare) {
    cases.push(goldenCase(id, `${ALTERNATIVE_PERIOD_DATASET}/without-compare-series`, defaultInputs(id, defaultPeriod), alternativeDataset));
    cases.push(goldenCase(id, `${COMPARE_DATASET}/compared-with-itself`, defaults, datasetByName.get(COMPARE_DATASET)!));
  }
  const header = JSON.stringify({ formula_version: CORE_INDICATOR_FORMULA_VERSION, id, name, default_period: defaultPeriod });
  return `${header.slice(0, -1)},"cases":[\n${cases.map((item) => JSON.stringify(item)).join(',\n')}\n]}\n`;
}

function datasetFile(dataset: GoldenDataset): string {
  const bars = dataset.bars.map((item) => JSON.stringify(item)).join(',\n');
  return `{"name":${JSON.stringify(dataset.name)},"bars":[${bars ? `\n${bars}\n` : ''}]}\n`;
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
      datasets: DATASET_NAMES,
      compare_datasets: COMPARE_DATASET_NAMES,
      indicators: AVAILABLE.map(({ id, name, defaultPeriod }) => ({ id, name, default_period: defaultPeriod })),
    }, null, 1)}\n`);
  });

  it.each([...DATASETS, ...COMPARE_DATASETS].map((dataset) => [dataset.name, dataset] as const))('dataset %s is stored', (name, dataset) => {
    expectFile(datasetPath(name), datasetFile(dataset));
  });

  it('records validation errors as expected errors', () => {
    const sma = AVAILABLE.find((definition) => definition.id === 'sma')!;
    const file = JSON.parse(indicatorFile(sma.id, sma.name, sma.defaultPeriod)) as { cases: GoldenCase[] };
    expect(file.cases.filter((item) => item.error).map((item) => item.case_id)).toEqual([
      `${INPUT_VARIANT_DATASET}/fractional-period`,
      `${INPUT_VARIANT_DATASET}/zero-period`,
    ]);
  });

  it.each(AVAILABLE.map((definition) => [definition.id, definition] as const))('%s matches its golden file', (id, definition) => {
    expectFile(join(GOLDEN_ROOT, 'indicators', `${id}.json`), indicatorFile(id, definition.name, definition.defaultPeriod));
  });
});
