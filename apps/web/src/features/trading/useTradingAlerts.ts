import { useQuery, useQueryClient } from '@tanstack/react-query';
import { tradingApi } from './tradingApi';
import type { TradingAlert } from './tradingTypes';

export const TRADING_ALERTS_QUERY_KEY = ['trading', 'alerts'] as const;

export function useTradingAlerts(options: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: TRADING_ALERTS_QUERY_KEY,
    queryFn: tradingApi.alerts,
    staleTime: 5_000,
    refetchInterval: options.poll ? 10_000 : false,
    refetchIntervalInBackground: options.poll ?? false,
  });
}

export function useTradingAlertMutations() {
  const queryClient = useQueryClient();

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: TRADING_ALERTS_QUERY_KEY });
  };

  const replace = (alert: TradingAlert) => {
    queryClient.setQueryData<TradingAlert[]>(TRADING_ALERTS_QUERY_KEY, (current = []) => {
      const exists = current.some((item) => item.alert_id === alert.alert_id);
      return exists
        ? current.map((item) => item.alert_id === alert.alert_id ? alert : item)
        : [alert, ...current];
    });
  };

  const remove = (alertId: string) => {
    queryClient.setQueryData<TradingAlert[]>(TRADING_ALERTS_QUERY_KEY, (current = []) => (
      current.filter((item) => item.alert_id !== alertId)
    ));
  };

  return { refresh, replace, remove };
}
