import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TradingIndicatorManager } from './TradingIndicatorManager';

describe('TradingIndicatorManager filters', () => {
  it('filters the catalog by market, category, and availability', () => {
    render(<TradingIndicatorManager indicators={[]} onToggle={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Indicators' }));

    const marketFilter = screen.getByLabelText('Market filter');
    const categoryFilter = screen.getByLabelText('Category filter');
    const availabilityFilter = screen.getByLabelText('Availability filter');

    fireEvent.change(marketFilter, { target: { value: 'crypto' } });
    expect(screen.getByText('Active addresses with contracts')).toBeTruthy();
    expect(screen.getByText('Relative Strength Index (RSI)')).toBeTruthy();
    expect(screen.queryByText('Analyst price forecast')).toBeNull();

    fireEvent.change(categoryFilter, { target: { value: 'on-chain' } });
    expect(screen.getByText('Active addresses with contracts')).toBeTruthy();
    expect(screen.queryByText('Relative Strength Index (RSI)')).toBeNull();

    fireEvent.change(categoryFilter, { target: { value: 'all' } });
    fireEvent.change(marketFilter, { target: { value: 'stocks' } });
    expect(screen.getByText('Analyst price forecast')).toBeTruthy();
    expect(screen.queryByText('Active addresses with contracts')).toBeNull();

    fireEvent.change(availabilityFilter, { target: { value: 'data-required' } });
    expect(screen.getByText('Analyst price forecast')).toBeTruthy();
    expect(screen.queryByText('Relative Strength Index (RSI)')).toBeNull();
  });

  it('makes the existing Fundamentals sidebar section useful', () => {
    render(<TradingIndicatorManager indicators={[]} onToggle={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Indicators' }));
    fireEvent.click(screen.getByRole('button', { name: 'Fundamentals' }));

    expect(screen.getByText('Analyst price forecast')).toBeTruthy();
    expect(screen.queryByText('Relative Strength Index (RSI)')).toBeNull();
  });
});
