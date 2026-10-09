// Alerts on any chart indicator and output (TVP-1.3). The alert dialog
// offers the chart's indicators, each with the output lines the chart draws;
// an indicator the server can't evaluate (or whose extra inputs it doesn't
// take yet) is offered greyed out with the reason. The alert is created as a
// conditions alert, so the server evaluates the same indicator, inputs and
// output on its own bars.
import type { CoreIndicatorInstance, IndicatorOutput } from './indicators/coreIndicators';
import { indicatorContextLabel } from './tradingChartPanelModel';
import type { components } from './api/generated';
import type { TradingAlertCreateInput } from './tradingTypes';

type ConditionInput = NonNullable<TradingAlertCreateInput['conditions']>[number];

export type AlertIndicatorOperator = 'crossing' | 'crossing_up' | 'crossing_down' | 'greater_than' | 'less_than';

export const ALERT_INDICATOR_OPERATORS: Array<{ value: AlertIndicatorOperator; label: string }> = [
  { value: 'crossing', label: 'Crossing' },
  { value: 'crossing_up', label: 'Crossing Up' },
  { value: 'crossing_down', label: 'Crossing Down' },
  { value: 'greater_than', label: 'Greater Than' },
  { value: 'less_than', label: 'Less Than' },
];

export type AlertIndicatorChoice = {
  /** The indicator id; one instance per id on a chart. */
  key: string;
  label: string;
  outputs: Array<{ key: string; title: string }>;
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
    const lines = outputs.filter((output) => output.key.split(':', 1)[0] === instance.id).map((output) => ({ key: output.key, title: output.title }));
    const unavailable = serverIds && !serverIds.has(instance.id)
      ? 'Server alerts are not available for this indicator yet'
      : instance.compareSymbol || (instance.params && Object.keys(instance.params).length > 0)
        ? 'Its extra inputs are not evaluated by server alerts yet'
        : lines.length === 0
          ? 'It draws no line to alert on'
          : undefined;
    return { key: instance.id, label: indicatorContextLabel(instance), outputs: lines, inputs: inputsOf(instance), ...(unavailable ? { unavailable } : {}) };
  });
}

/** The condition an indicator selection describes: the output against a value. */
export function indicatorConditionSpec(choice: AlertIndicatorChoice, selection: AlertIndicatorSelection, value: string): ConditionInput {
  return {
    source: { kind: 'indicator', indicator_id: choice.key, inputs: choice.inputs, output: selection.output },
    operator: selection.operator,
    target: { kind: 'value', value },
  };
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

/** The selection a dialog starts with: the first indicator the server can alert on, its first line, crossing. */
export function defaultIndicatorSelection(choices: readonly AlertIndicatorChoice[]): AlertIndicatorSelection | undefined {
  const choice = choices.find((item) => !item.unavailable);
  return choice ? { key: choice.key, output: choice.outputs[0].key, operator: 'crossing' } : undefined;
}
