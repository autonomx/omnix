// Alerts on any chart indicator and output (TVP-1.3). The alert dialog
// offers the chart's indicators, each with the output lines the chart draws;
// an indicator the server can't evaluate (or whose extra inputs it doesn't
// take yet) is offered greyed out with the reason. The alert is created as a
// conditions alert, so the server evaluates the same indicator, inputs and
// output on its own bars.
import type { CoreIndicatorInstance, IndicatorOutput } from './indicators/coreIndicators';
import { tradingViewBuiltInUsesSessions } from './indicators/tradingViewBuiltIns';
import { indicatorContextLabel } from './tradingChartPanelModel';
import type { components } from './api/generated';
import type { TradingAlertCreateInput } from './tradingTypes';

type ConditionInput = NonNullable<TradingAlertCreateInput['conditions']>[number];

/** `appears`: a signal output (markers: candlestick patterns, fractals) has a value on this bar; stored as greater than 0. */
export type AlertIndicatorOperator = 'crossing' | 'crossing_up' | 'crossing_down' | 'greater_than' | 'less_than' | 'appears';

export const ALERT_INDICATOR_OPERATORS: Array<{ value: AlertIndicatorOperator; label: string }> = [
  { value: 'crossing', label: 'Crossing' },
  { value: 'crossing_up', label: 'Crossing Up' },
  { value: 'crossing_down', label: 'Crossing Down' },
  { value: 'greater_than', label: 'Greater Than' },
  { value: 'less_than', label: 'Less Than' },
];
/** The comparison a signal output offers: it has a value only on the bars where the signal appears. */
export const ALERT_SIGNAL_OPERATORS: Array<{ value: AlertIndicatorOperator; label: string }> = [{ value: 'appears', label: 'Appears' }];

export type AlertIndicatorChoice = {
  /** The indicator id; one instance per id on a chart. */
  key: string;
  label: string;
  /** `signal`: drawn as markers, valued (at the bar's price) only on the bars where it appears. */
  outputs: Array<{ key: string; title: string; signal?: true }>;
  inputs: components['schemas']['IndicatorSourceInputs'];
  /** Why the server can't alert on it, when it can't. */
  unavailable?: string;
};

/** What the dialog holds for a chart-indicator condition. */
export type AlertIndicatorSelection = { key: string; output: string; operator: AlertIndicatorOperator };

function inputsOf(instance: CoreIndicatorInstance): AlertIndicatorChoice['inputs'] {
  return {
    period: instance.period,
    fast_period: instance.fastPeriod ?? null,
    slow_period: instance.slowPeriod ?? null,
    signal_period: instance.signalPeriod ?? null,
    standard_deviations: instance.standardDeviations ?? null,
    anchor_time: instance.anchorTime || null,
    anchor_bars_ago: null,
  };
}

/** The chart's enabled indicators as alert sources; `serverIds` null while the server's list loads. */
export function alertIndicatorChoices(
  instances: readonly CoreIndicatorInstance[],
  outputs: readonly IndicatorOutput[],
  serverIds: ReadonlySet<string> | null,
): AlertIndicatorChoice[] {
  return instances.filter((instance) => instance.enabled).map((instance) => {
    const lines = outputs.filter((output) => output.key.split(':', 1)[0] === instance.id)
      .map((output) => ({ key: output.key, title: output.title, ...(output.render === 'markers' ? { signal: true as const } : {}) }));
    const unavailable = serverIds === null
      ? 'Checking which indicators server alerts support…'
      : !serverIds.has(instance.id)
        ? 'Server alerts are not available for this indicator yet'
        // The server evaluates session-based indicators on UTC days; the chart draws them on the market's sessions.
        : tradingViewBuiltInUsesSessions(instance.id)
          ? 'It uses the market sessions, which server alerts do not follow yet'
          : instance.compareSymbol || (instance.params && Object.keys(instance.params).length > 0)
        ? 'Its extra inputs are not evaluated by server alerts yet'
        : lines.length === 0
          ? 'It draws no line to alert on'
          : undefined;
    return { key: instance.id, label: indicatorContextLabel(instance), outputs: lines, inputs: inputsOf(instance), ...(unavailable ? { unavailable } : {}) };
  });
}

/** The condition an indicator selection describes: the output against a value; "appears" is the output above 0. */
export function indicatorConditionSpec(choice: AlertIndicatorChoice, selection: AlertIndicatorSelection, value: string): ConditionInput {
  const appears = selection.operator === 'appears';
  return {
    source: { kind: 'indicator', indicator_id: choice.key, inputs: choice.inputs, output: selection.output },
    operator: selection.operator === 'appears' ? 'greater_than' : selection.operator,
    target: { kind: 'value', value: appears ? '0' : value },
  };
}

/** The operator a selection keeps on another output: "appears" for a signal, else the line's comparison (crossing by default). */
export function operatorForOutput(choice: AlertIndicatorChoice | undefined, output: string, operator: AlertIndicatorOperator | undefined): AlertIndicatorOperator {
  const signal = choice?.outputs.find((item) => item.key === output)?.signal === true;
  if (signal) return 'appears';
  return operator && operator !== 'appears' ? operator : 'crossing';
}

/**
 * Turns a create request into a conditions alert on the selected chart indicator, when the dialog has one; returns
 * whether it did. The legacy indicator fields are cleared: the condition says everything.
 */
export function withChartIndicatorCondition(
  input: TradingAlertCreateInput,
  choices: readonly AlertIndicatorChoice[] | undefined,
  selection: AlertIndicatorSelection | undefined,
  value: string,
): boolean {
  const choice = selection ? choices?.find((item) => item.key === selection.key && !item.unavailable) : undefined;
  if (!choice || !selection || !choice.outputs.some((output) => output.key === selection.output)) return false;
  input.condition_type = 'conditions';
  input.threshold = '0';
  input.conditions = [indicatorConditionSpec(choice, selection, value)];
  input.parameters = { ...input.parameters, indicator_id: null };
  return true;
}

/** The selection a dialog starts with: the indicator the alert was placed on, else the first the server can alert on. */
export function defaultIndicatorSelection(choices: readonly AlertIndicatorChoice[], preferKey?: string): AlertIndicatorSelection | undefined {
  // Placed on a pane whose indicator can't be alerted on: no stand-in (its value is on another scale); the user picks.
  if (preferKey && choices.some((item) => item.key === preferKey && item.unavailable)) return undefined;
  const choice = choices.find((item) => item.key === preferKey && !item.unavailable) ?? choices.find((item) => !item.unavailable);
  return choice ? { key: choice.key, output: choice.outputs[0].key, operator: operatorForOutput(choice, choice.outputs[0].key, undefined) } : undefined;
}

/**
 * A selection that still fits the chart: an indicator that went away (or became unavailable) falls back to the
 * default, a line that went away to the indicator's first line. Undefined when nothing can be alerted on.
 */
export function resolveIndicatorSelection(
  choices: readonly AlertIndicatorChoice[],
  selection: AlertIndicatorSelection | undefined,
  preferKey?: string,
): AlertIndicatorSelection | undefined {
  const choice = selection ? choices.find((item) => item.key === selection.key && !item.unavailable) : undefined;
  if (!choice || !selection) return defaultIndicatorSelection(choices, preferKey);
  const output = choice.outputs.some((item) => item.key === selection.output) ? selection.output : choice.outputs[0].key;
  return { ...selection, output, operator: operatorForOutput(choice, output, selection.operator) };
}

type ChartAlert = { condition_type: string; threshold: string | number; parameters: { indicator_id?: string | null }; conditions?: readonly unknown[] };
type IndicatorValueCondition = { source: { kind: string; indicator_id?: string }; target?: { kind: string; value?: string | number } };

function singleIndicatorCondition(alert: ChartAlert): IndicatorValueCondition | null {
  if (alert.condition_type !== 'conditions' || alert.conditions?.length !== 1) return null;
  const condition = alert.conditions[0] as IndicatorValueCondition;
  return condition.source.kind === 'indicator' && condition.target?.kind === 'value' ? condition : null;
}

/** The indicator an alert is drawn on: a legacy indicator alert's, or a single "indicator line vs value" condition's. */
export function chartAlertIndicatorId(alert: ChartAlert): string | null {
  if (alert.condition_type.startsWith('indicator_')) return alert.parameters.indicator_id ?? null;
  return singleIndicatorCondition(alert)?.source.indicator_id ?? null;
}

/** The value an alert is drawn at: its threshold, or its single indicator condition's value. */
export function chartAlertThreshold(alert: ChartAlert): number {
  const condition = singleIndicatorCondition(alert);
  return Number(condition ? condition.target?.value : alert.threshold);
}

/** An alert's conditions with the single indicator condition moved to `value` (a dragged line). */
export function conditionsAtValue<T extends ChartAlert>(alert: T, value: string): T['conditions'] {
  if (!singleIndicatorCondition(alert)) return alert.conditions;
  const [condition] = alert.conditions as IndicatorValueCondition[];
  return [{ ...condition, target: { kind: 'value', value } }] as T['conditions'];
}
