import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render as renderPlain, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradingIndicatorSettings } from './TradingIndicatorSettings';

afterEach(cleanup);

const render = (element: ReactElement) => renderPlain(<QueryClientProvider client={new QueryClient()}>{element}</QueryClientProvider>);

describe('indicator source input (TVP-6.5)', () => {
  it('reads another indicator line instead of the close', () => {
    const onApply = vi.fn();
    render(
      <TradingIndicatorSettings
        indicator={{ id: 'sma', period: 10, enabled: true }}
        sourceChoices={[{ value: 'rsi:14', label: 'RSI', ref: { indicatorId: 'rsi', output: 'rsi:14' } }]}
        onApply={onApply}
        onClose={() => undefined}
      />,
    );
    const select = screen.getByLabelText('Indicator source') as HTMLSelectElement;
    expect(select.value).toBe('');
    fireEvent.change(select, { target: { value: 'rsi:14' } });
    fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ source: { indicatorId: 'rsi', output: 'rsi:14' } }));
  });

  it('has no source input for an indicator that takes none', () => {
    render(<TradingIndicatorSettings indicator={{ id: 'atr', period: 14, enabled: true }} onApply={() => undefined} onClose={() => undefined} />);
    expect(screen.queryByLabelText('Indicator source')).toBeNull();
  });
});
