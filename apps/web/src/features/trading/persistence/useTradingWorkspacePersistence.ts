import { useEffect, useRef, useState } from 'react';
import { tradingApi } from '../tradingApi';
import { useTradingStore } from '../tradingStore';
import type { TradingDocument } from '../tradingTypes';
import { tradingDraftRecovery } from './draftRecovery';
import { parseTradingWorkspace, serializeTradingWorkspace } from './workspaceDocument';

export type WorkspacePersistenceStatus = 'loading' | 'saved' | 'saving' | 'draft' | 'conflict' | 'error';

export function useTradingWorkspacePersistence(): WorkspacePersistenceStatus {
  const [status, setStatus] = useState<WorkspacePersistenceStatus>('loading');
  const recordRef = useRef<TradingDocument | null>(null);

  useEffect(() => {
    let cancelled = false;
    let saveTimer: ReturnType<typeof setTimeout> | null = null;
    let unsubscribe: () => void = () => {};

    const currentPayload = () => {
      const state = useTradingStore.getState();
      return serializeTradingWorkspace({
        layout: state.layout,
        activeChartId: state.activeChartId,
        charts: state.charts,
        links: state.links,
      });
    };

    const hydrate = (value: unknown) => {
      const payload = parseTradingWorkspace(value);
      if (!payload) return false;
      useTradingStore.setState({
        layout: payload.layout,
        activeChartId: payload.activeChartId,
        charts: payload.charts,
        links: payload.links,
      });
      return true;
    };

    const save = async () => {
      if (cancelled) return;
      setStatus('saving');
      const payload = currentPayload();
      try {
        const record = recordRef.current;
        const next = record
          ? await tradingApi.updateDocument('workspaces', record, payload as unknown as Record<string, unknown>)
          : await tradingApi.createDocument('workspaces', 'main', payload as unknown as Record<string, unknown>);
        if (cancelled) return;
        recordRef.current = next;
        await tradingDraftRecovery.clear();
        setStatus('saved');
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : String(error);
        if (message.includes('(409)')) {
          setStatus('conflict');
          const latest = await tradingApi.documents('workspaces').catch(() => []);
          recordRef.current = latest.find((record) => record.record_id === 'main') ?? recordRef.current;
        } else {
          setStatus('error');
        }
      }
    };

    const initialize = async () => {
      try {
        const [records, draft] = await Promise.all([
          tradingApi.documents('workspaces'),
          tradingDraftRecovery.load().catch(() => null),
        ]);
        if (cancelled) return;
        const record = records.find((item) => item.record_id === 'main') ?? null;
        recordRef.current = record;
        const hydratedServer = record ? hydrate(record.payload) : false;
        if (!hydratedServer && draft) hydrate(draft);
        if (!record) {
          recordRef.current = await tradingApi.createDocument(
            'workspaces',
            'main',
            currentPayload() as unknown as Record<string, unknown>,
          );
        }
        if (cancelled) return;
        setStatus('saved');
        unsubscribe = useTradingStore.subscribe((state) => {
          const payload = serializeTradingWorkspace({
            layout: state.layout,
            activeChartId: state.activeChartId,
            charts: state.charts,
            links: state.links,
          });
          setStatus('draft');
          void tradingDraftRecovery.save(payload).catch(() => undefined);
          if (saveTimer) clearTimeout(saveTimer);
          saveTimer = setTimeout(() => void save(), 700);
        });
      } catch {
        if (!cancelled) setStatus('error');
      }
    };

    void initialize();
    return () => {
      cancelled = true;
      unsubscribe();
      if (saveTimer) clearTimeout(saveTimer);
    };
  }, []);

  return status;
}
