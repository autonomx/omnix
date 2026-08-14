export type TradingIntervalOption = {
  value: string;
  label: string;
  compactLabel: string;
};

export type TradingIntervalGroup = {
  label: string;
  options: readonly TradingIntervalOption[];
};

const options = (items: readonly [string, string, string][]): readonly TradingIntervalOption[] => (
  items.map(([value, label, compactLabel]) => ({ value, label, compactLabel }))
);

export const TRADING_VIEW_INTERVAL_GROUPS: readonly TradingIntervalGroup[] = [
  {
    label: 'Ticks',
    options: options([
      ['1t', '1 tick', '1T'],
      ['10t', '10 ticks', '10T'],
      ['100t', '100 ticks', '100T'],
      ['1000t', '1000 ticks', '1000T'],
    ]),
  },
  {
    label: 'Seconds',
    options: options([
      ['1s', '1 second', '1s'],
      ['5s', '5 seconds', '5s'],
      ['10s', '10 seconds', '10s'],
      ['15s', '15 seconds', '15s'],
      ['30s', '30 seconds', '30s'],
      ['45s', '45 seconds', '45s'],
    ]),
  },
  {
    label: 'Minutes',
    options: options([
      ['1m', '1 minute', '1m'],
      ['2m', '2 minutes', '2m'],
      ['3m', '3 minutes', '3m'],
      ['5m', '5 minutes', '5m'],
      ['10m', '10 minutes', '10m'],
      ['15m', '15 minutes', '15m'],
      ['30m', '30 minutes', '30m'],
      ['45m', '45 minutes', '45m'],
    ]),
  },
  {
    label: 'Hours',
    options: options([
      ['1h', '1 hour', '1H'],
      ['2h', '2 hours', '2H'],
      ['3h', '3 hours', '3H'],
      ['4h', '4 hours', '4H'],
      ['6h', '6 hours', '6H'],
      ['7h', '7 hours', '7H'],
      ['8h', '8 hours', '8H'],
      ['12h', '12 hours', '12H'],
      ['20h', '20 hours', '20H'],
      ['24h', '24 hours', '24H'],
    ]),
  },
  {
    label: 'Days',
    options: options([
      ['1d', '1 day', '1D'],
      ['2d', '2 days', '2D'],
      ['3d', '3 days', '3D'],
      ['4d', '4 days', '4D'],
      ['5d', '5 days', '5D'],
      ['6d', '6 days', '6D'],
    ]),
  },
  {
    label: 'Weeks',
    options: options([
      ['1w', '1 week', '1W'],
      ['2w', '2 weeks', '2W'],
      ['3w', '3 weeks', '3W'],
      ['6w', '6 weeks', '6W'],
    ]),
  },
  {
    label: 'Months',
    options: options([
      ['1mo', '1 month', '1M'],
      ['2mo', '2 months', '2M'],
      ['3mo', '3 months', '3M'],
      ['6mo', '6 months', '6M'],
      ['12mo', '12 months', '12M'],
    ]),
  },
  {
    label: 'Ranges',
    options: options([
      ['1r', '1 range', '1R'],
      ['10r', '10 ranges', '10R'],
      ['100r', '100 ranges', '100R'],
      ['1000r', '1000 ranges', '1000R'],
    ]),
  },
] as const;

const optionByValue = new Map(
  TRADING_VIEW_INTERVAL_GROUPS.flatMap((group) => group.options).map((option) => [option.value, option]),
);

export function intervalMenuLabel(interval: string): string {
  return optionByValue.get(interval)?.label ?? interval.toUpperCase();
}

export function intervalCompactLabel(interval: string): string {
  return optionByValue.get(interval)?.compactLabel ?? (interval === '1mo' ? '1M' : interval.toUpperCase());
}
