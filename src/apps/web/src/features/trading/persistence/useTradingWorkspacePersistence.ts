import { useCallback, useEffect, useRef, useState } from 'react';
import { tradingApi } from '../tradingApi';
import { useTradingStore } from '../tradingStore';
import type { TradingDocument } from '../tradingTypes';
import { tradingDraftRecovery } from './draftRecovery';
import {
  parseTradingWorkspace,
  serializeTradingWorkspace,
  type TradingWorkspacePayload,
} from './workspaceDocument';

export type WorkspacePersistenceStatus = 'loading' | 'saved' | 'saving' | 'draft' | 'conflict' | 'error';
export type TradingWorkspaceSummary = { workspaceId: string; name: string; revision: number };

type ConflictState = {
  localPayload: TradingWorkspacePayload;
  serverRecord: TradingDocument | null;
  serverPayload: TradingWorkspacePayload | null;
};

export type TradingWorkspacePersistence = {
  status: WorkspacePersistenceStatus;
  workspaces: TradingWorkspaceSummary[];
  activeWorkspaceId: string;
  activeWorkspaceName: string;
  hasConflict: boolean;
  selectWorkspace: (workspaceId: string) => Promise<void>;
  createWorkspace: (name: string) => Promise<void>;
  renameWorkspace: (name: string) => Promise<void>;
  deleteWorkspace: () => Promise<void>;
  resolveConflict: (resolution: 'reload' | 'overwrite') => Promise<void>;
};

function safeWorkspace(record: TradingDocument | null): TradingWorkspacePayload | null {
  return record ? parseTradingWorkspace(record.payload) : null;
}

function summary(record: TradingDocument): TradingWorkspaceSummary {
  return {
    workspaceId: record.record_id,
    name: safeWorkspace(record)?.name ?? record.record_id,
    revision: record.revision,
  };
}

function workspaceId(name: string): string {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48) || 'workspace';
  return `${slug}-${crypto.randomUUID().slice(0, 8)}`;
}

export function useTradingWorkspacePersistence(): TradingWorkspacePersistence {
  const [status, setStatus] = useState<WorkspacePersistenceStatus>('loading');
  const [workspaces, setWorkspaces] = useState<TradingWorkspaceSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState('');
  const recordsRef = useRef<Map<string, TradingDocument>>(new Map());
  const activeIdRef = useRef('');
  const conflictRef = useRef<ConflictState | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const applyingRef = useRef(false);
  const cancelledRef = useRef(false);

  const refreshSummaries = useCallback(() => {
    setWorkspaces([...recordsRef.current.values()].map(summary).sort((left, right) => left.name.localeCompare(right.name)));
  }, []);

  const activeName = useCallback(() => {
    const record = recordsRef.current.get(activeIdRef.current) ?? null;
    return safeWorkspace(record)?.name ?? 'Main Workspace';
  }, []);

  const currentPayload = useCallback((name = activeName()) => {
    const state = useTradingStore.getState();
    return serializeTradingWorkspace({
      name,
      layout: state.layout,
      activeChartId: state.activeChartId,
      charts: state.charts,
      links: state.links,
      panels: state.panels,
      favoriteInstrumentIds: state.favoriteInstrumentIds,
    });
  }, [activeName]);

  const hydrate = useCallback((value: unknown): boolean => {
    const payload = parseTradingWorkspace(value);
    if (!payload) return false;
    applyingRef.current = true;
    useTradingStore.setState({
      layout: payload.layout,
      activeChartId: payload.activeChartId,
      replayMode: false,
      charts: payload.charts,
      links: payload.links,
      panels: payload.panels,
      favoriteInstrumentIds: payload.favoriteInstrumentIds,
    });
    applyingRef.current = false;
    return true;
  }, []);

  const loadLatestRecord = useCallback(async (id: string): Promise<TradingDocument | null> => {
    const records = await tradingApi.documents('workspaces').catch(() => []);
    for (const record of records) recordsRef.current.set(record.record_id, record);
    refreshSummaries();
    return records.find((record) => record.record_id === id) ?? null;
  }, [refreshSummaries]);

  const savePayload = useCallback(async (
    record: TradingDocument,
    payload: TradingWorkspacePayload,
  ): Promise<TradingDocument | null> => {
    setStatus('saving');
    try {
      const saved = await tradingApi.updateDocument('workspaces', record, payload as unknown as Record<string, unknown>);
      if (cancelledRef.current) return null;
      recordsRef.current.set(saved.record_id, saved);
      conflictRef.current = null;
      await tradingDraftRecovery.clear();
      refreshSummaries();
      setStatus('saved');
      return saved;
    } catch (error) {
      if (cancelledRef.current) return null;
      if (error instanceof Error && error.message.includes('(409)')) {
        const latest = await loadLatestRecord(record.record_id);
        conflictRef.current = {
          localPayload: payload,
          serverRecord: latest,
          serverPayload: safeWorkspace(latest),
        };
        setStatus('conflict');
      } else {
        setStatus('error');
      }
      return null;
    }
  }, [loadLatestRecord, refreshSummaries]);

  const saveActive = useCallback(async (): Promise<void> => {
    const id = activeIdRef.current;
    const record = recordsRef.current.get(id);
    if (!record || conflictRef.current) return;
    await savePayload(record, currentPayload());
  }, [currentPayload, savePayload]);

  useEffect(() => {
    cancelledRef.current = false;
    // React StrictMode intentionally mounts effects twice in development. The
    // first async initializer must remain cancelled even after the second
    // mount resets the shared cancellation ref; otherwise both initializers
    // can observe an empty list and race to create `main`.
    let disposed = false;
    let unsubscribe: () => void = () => {};

    const initialize = async () => {
      try {
        const [records, draft] = await Promise.all([
          tradingApi.documents('workspaces'),
          tradingDraftRecovery.load().catch(() => null),
        ]);
        if (disposed || cancelledRef.current) return;
        recordsRef.current = new Map(records.map((record) => [record.record_id, record]));
        let record = records.find((item) => item.record_id === 'main') ?? records[0] ?? null;
        if (!record) {
          if (draft) hydrate(draft);
          const created = await tradingApi.createDocument(
            'workspaces',
            'main',
            currentPayload('Main Workspace') as unknown as Record<string, unknown>,
          );
          if (disposed || cancelledRef.current) return;
          recordsRef.current.set(created.record_id, created);
          record = created;
        }
        if (disposed || cancelledRef.current) return;
        activeIdRef.current = record.record_id;
        setActiveWorkspaceId(record.record_id);
        if (!hydrate(record.payload) && draft) hydrate(draft);
        refreshSummaries();
        setStatus('saved');

        unsubscribe = useTradingStore.subscribe(() => {
          if (applyingRef.current || cancelledRef.current) return;
          const payload = currentPayload();
          void tradingDraftRecovery.save(payload).catch(() => undefined);
          if (conflictRef.current) {
            conflictRef.current.localPayload = payload;
            setStatus('conflict');
            return;
          }
          setStatus('draft');
          if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
          saveTimerRef.current = setTimeout(() => void saveActive(), 700);
        });
      } catch {
        if (!disposed && !cancelledRef.current) setStatus('error');
      }
    };

    void initialize();
    return () => {
      disposed = true;
      cancelledRef.current = true;
      unsubscribe();
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [currentPayload, hydrate, refreshSummaries, saveActive]);

  const selectWorkspace = useCallback(async (id: string) => {
    if (id === activeIdRef.current || !recordsRef.current.has(id)) return;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (!conflictRef.current) await saveActive();
    const record = recordsRef.current.get(id);
    if (!record || !hydrate(record.payload)) return;
    activeIdRef.current = id;
    setActiveWorkspaceId(id);
    conflictRef.current = null;
    setStatus('saved');
  }, [hydrate, saveActive]);

  const createWorkspace = useCallback(async (name: string) => {
    const cleanName = name.trim();
    if (!cleanName) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    if (!conflictRef.current) await saveActive();
    setStatus('saving');
    try {
      const id = workspaceId(cleanName);
      const created = await tradingApi.createDocument(
        'workspaces',
        id,
        currentPayload(cleanName) as unknown as Record<string, unknown>,
      );
      recordsRef.current.set(id, created);
      activeIdRef.current = id;
      setActiveWorkspaceId(id);
      conflictRef.current = null;
      refreshSummaries();
      setStatus('saved');
    } catch {
      setStatus('error');
    }
  }, [currentPayload, refreshSummaries, saveActive]);

  const renameWorkspace = useCallback(async (name: string) => {
    const cleanName = name.trim();
    const record = recordsRef.current.get(activeIdRef.current);
    if (!record || !cleanName) return;
    await savePayload(record, currentPayload(cleanName));
  }, [currentPayload, savePayload]);

  const deleteWorkspace = useCallback(async () => {
    if (recordsRef.current.size <= 1) return;
    const current = recordsRef.current.get(activeIdRef.current);
    if (!current) return;
    setStatus('saving');
    try {
      await tradingApi.archiveDocument('workspaces', current);
      recordsRef.current.delete(current.record_id);
      const next = [...recordsRef.current.values()][0];
      activeIdRef.current = next.record_id;
      setActiveWorkspaceId(next.record_id);
      hydrate(next.payload);
      conflictRef.current = null;
      refreshSummaries();
      setStatus('saved');
    } catch (error) {
      if (error instanceof Error && error.message.includes('(409)')) {
        await loadLatestRecord(current.record_id);
        setStatus('conflict');
      } else {
        setStatus('error');
      }
    }
  }, [hydrate, loadLatestRecord, refreshSummaries]);

  const resolveConflict = useCallback(async (resolution: 'reload' | 'overwrite') => {
    const conflict = conflictRef.current;
    if (!conflict) return;
    if (resolution === 'reload') {
      if (conflict.serverPayload) hydrate(conflict.serverPayload);
      conflictRef.current = null;
      await tradingDraftRecovery.clear();
      setStatus('saved');
      return;
    }
    if (!conflict.serverRecord) {
      setStatus('error');
      return;
    }
    await savePayload(conflict.serverRecord, conflict.localPayload);
  }, [hydrate, savePayload]);

  const activeWorkspaceName = workspaces.find((workspace) => workspace.workspaceId === activeWorkspaceId)?.name
    ?? activeName();

  return {
    status,
    workspaces,
    activeWorkspaceId,
    activeWorkspaceName,
    hasConflict: status === 'conflict',
    selectWorkspace,
    createWorkspace,
    renameWorkspace,
    deleteWorkspace,
    resolveConflict,
  };
}
