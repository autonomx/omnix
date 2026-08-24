import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TradingMarketDataSettings } from './TradingMarketDataSettings';

const mockedApi = vi.hoisted(() => ({
  coinmarketcapCredentials: vi.fn(),
  saveCoinMarketCapCredentials: vi.fn(),
}));

vi.mock('./tradingMarketDataApi', () => ({ tradingMarketDataApi: mockedApi }));

const configured = {
  provider: 'coinmarketcap' as const,
  configured: true,
  api_key_masked: '***5678',
  api_key_source: 'os_protected_store' as const,
  api_key_editable: true,
  storage: 'Windows DPAPI user store',
};

describe('TradingMarketDataSettings', () => {
  beforeEach(() => {
    mockedApi.coinmarketcapCredentials.mockReset();
    mockedApi.saveCoinMarketCapCredentials.mockReset();
  });

  it('loads masked status and saves a new key without rendering the secret', async () => {
    mockedApi.coinmarketcapCredentials.mockResolvedValue(configured);
    mockedApi.saveCoinMarketCapCredentials.mockResolvedValue(configured);
    render(<TradingMarketDataSettings />);

    expect(await screen.findByText('CoinMarketCap market-cap data is configured.')).toBeVisible();
    expect(screen.getByPlaceholderText('***5678')).toBeVisible();

    fireEvent.change(screen.getByLabelText('CoinMarketCap API key'), { target: { value: 'new-secret-key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save key' }));

    expect(await screen.findByText('CoinMarketCap API key saved in the OS-protected store.')).toBeVisible();
    expect(mockedApi.saveCoinMarketCapCredentials).toHaveBeenCalledWith({ api_key: 'new-secret-key' });
    expect(screen.queryByDisplayValue('new-secret-key')).not.toBeInTheDocument();
  });
});
