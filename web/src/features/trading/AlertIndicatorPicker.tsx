import { ALERT_INDICATOR_OPERATORS, type AlertIndicatorChoice, type AlertIndicatorOperator, type AlertIndicatorSelection } from './alertIndicatorSources';

/** The chart's indicators, their output lines and the comparison, for an indicator alert (TVP-1.3). */
export function AlertIndicatorPicker({
  choices, selection, onChange,
}: {
  choices: readonly AlertIndicatorChoice[];
  selection: AlertIndicatorSelection | undefined;
  onChange: (selection: AlertIndicatorSelection) => void;
}) {
  const choice = choices.find((item) => item.key === selection?.key);
  const pick = (key: string) => {
    const next = choices.find((item) => item.key === key);
    if (next && !next.unavailable) onChange({ key, output: next.outputs[0].key, operator: selection?.operator ?? 'crossing' });
  };
  return (
    <>
      <div className="trading-alert-condition-row">
        <select aria-label="Alert chart indicator" value={selection?.key ?? ''} onChange={(event) => pick(event.target.value)}>
          {selection ? null : <option value="" disabled>Choose an indicator</option>}
          {choices.map((item) => (
            <option key={item.key} value={item.key} disabled={Boolean(item.unavailable)} title={item.unavailable}>
              {item.label}{item.unavailable ? ` — ${item.unavailable}` : ''}
            </option>
          ))}
        </select>
        <select
          aria-label="Alert indicator line"
          value={selection?.output ?? ''}
          disabled={!choice}
          onChange={(event) => selection && onChange({ ...selection, output: event.target.value })}
        >
          {(choice?.outputs ?? []).map((output) => <option key={output.key} value={output.key}>{output.title}</option>)}
        </select>
      </div>
      <div className="trading-alert-condition-row">
        <select
          aria-label="Alert indicator comparison"
          value={selection?.operator ?? 'crossing'}
          disabled={!selection}
          onChange={(event) => selection && onChange({ ...selection, operator: event.target.value as AlertIndicatorOperator })}
        >
          {ALERT_INDICATOR_OPERATORS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </div>
    </>
  );
}
