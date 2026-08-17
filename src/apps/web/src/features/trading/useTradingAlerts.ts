import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { tradingApi } from './tradingApi';
import type { TradingAlert } from './tradingTypes';

export const TRADING_ALERTS_QUERY_KEY = ['trading', 'alerts'] as const;
export const TRADING_ALERT_TRIGGERS_QUERY_KEY = ['trading', 'alert-triggers'] as const;

let pollSubscribers = 0;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let triggerPollSubscribers = 0;
let triggerPollTimer: ReturnType<typeof setInterval> | null = null;

export function useTradingAlerts(options: { poll?: boolean } = {}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: TRADING_ALERTS_QUERY_KEY,
    queryFn: tradingApi.alerts,
    staleTime: 5_000,
  });

  useEffect(() => {
    if (!options.poll) return;
    pollSubscribers += 1;
    if (!pollTimer) {
      pollTimer = setInterval(() => {
        void queryClient.invalidateQueries({ queryKey: TRADING_ALERTS_QUERY_KEY });
      }, 10_000);
    }
    return () => {
      pollSubscribers = Math.max(0, pollSubscribers - 1);
      if (pollSubscribers === 0 && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    };
  }, [options.poll, queryClient]);

  return query;
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

  return { refresh, replace };
}

export function useTradingAlertTriggers(options: { poll?: boolean } = {}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: TRADING_ALERT_TRIGGERS_QUERY_KEY,
    queryFn: tradingApi.alertTriggers,
    staleTime: 5_000,
  });

  useEffect(() => {
    if (!options.poll) return;
    triggerPollSubscribers += 1;
    if (!triggerPollTimer) {
      triggerPollTimer = setInterval(() => {
        void queryClient.invalidateQueries({ queryKey: TRADING_ALERT_TRIGGERS_QUERY_KEY });
      }, 10_000);
    }
    return () => {
      triggerPollSubscribers = Math.max(0, triggerPollSubscribers - 1);
      if (triggerPollSubscribers === 0 && triggerPollTimer) {
        clearInterval(triggerPollTimer);
        triggerPollTimer = null;
      }
    };
  }, [options.poll, queryClient]);

  return query;
}
