import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TradingPinePanel } from './TradingPinePanel';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';

const sma: CoreIndicatorInstance = { id: 'sma', period: 20, enabled: true };

describe('TradingPinePanel', () => {
  it('labels the source as Pine-compatible script source, not as Pine Script', () => {
    render(<TradingPinePanel indicators={[sma]} activeIndicatorId="sma" onActiveIndicatorChange={vi.fn()} />);

    const source = screen.getByRole('textbox', { name: 'Script source (Pine-compatible)' });
    expect(source).toHaveAttribute('aria-readonly', 'true');
    expect(source).toHaveTextContent('//@version=6');
    expect(screen.queryByRole('textbox', { name: 'Pine Script source' })).not.toBeInTheDocument();
  });

  it('shows an empty state when no indicator is enabled', () => {
    render(<TradingPinePanel indicators={[{ ...sma, enabled: false }]} activeIndicatorId={null} onActiveIndicatorChange={vi.fn()} />);

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
