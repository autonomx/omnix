import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TradingPinePanel } from './TradingPinePanel';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';

const sma: CoreIndicatorInstance = { id: 'sma', period: 20, enabled: true };

describe('TradingPinePanel', () => {
  it('names the product Omnix Scripts and the source Pine-compatible', () => {
    render(<TradingPinePanel indicators={[sma]} activeIndicatorId="sma" onActiveIndicatorChange={vi.fn()} />);

    expect(screen.getByRole('group', { name: 'Omnix Scripts editor' })).toBeInTheDocument();
    expect(screen.getByText('Omnix Scripts')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Script indicator' })).toHaveValue('sma');
    expect(screen.getByText(/Pine-compatible v6/)).toBeInTheDocument();
    const source = screen.getByRole('textbox', { name: 'Script source (Pine-compatible)' });
    expect(source).toHaveAttribute('aria-readonly', 'true');
    expect(source).toHaveTextContent('//@version=6');
    expect(screen.queryByText(/Pine Editor|Pine Script/)).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Pine Script source' })).not.toBeInTheDocument();
  });

  it('shows an empty state when no indicator is enabled', () => {
    render(<TradingPinePanel indicators={[{ ...sma, enabled: false }]} activeIndicatorId={null} onActiveIndicatorChange={vi.fn()} />);

    expect(screen.getByText('Add an indicator to view its Pine-compatible script source.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
