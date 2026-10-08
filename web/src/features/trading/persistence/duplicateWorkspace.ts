import { tradingDrawingRecordId } from '../drawings/useTradingDrawings';
import { tradingApi } from '../tradingApi';
import { useTradingStore } from '../tradingStore';
import type { TradingDocument } from '../tradingTypes';
import { currentTradingWorkspaceScopeId, type TradingWorkspacePersistence } from './useTradingWorkspacePersistence';

const INSTRUMENT_MARKER = 'instrument-';

/** The record-id prefix of a workspace tab's drawing documents (see `tradingDrawingRecordId`). */
function drawingScopePrefix(workspaceId: string, tabScopeId: string): string {
  const sample = tradingDrawingRecordId('', `${workspaceId}:${tabScopeId}`);
  return sample.slice(0, sample.length - INSTRUMENT_MARKER.length);
}

/**
 * The drawing documents to create so a duplicated workspace starts with the source's drawings.
 * Drawing documents are scoped by workspace and tab; the duplicate keeps the tab ids, so each
 * source record maps to the same record id under the new workspace.
 */
export function workspaceDrawingCopies(
  records: readonly TradingDocument[],
  sourceWorkspaceId: string,
  targetWorkspaceId: string,
  tabIds: readonly string[],
): Array<{ recordId: string; payload: Record<string, unknown> }> {
  const scopes = [...new Set([...tabIds, 'global'])];
  const copies: Array<{ recordId: string; payload: Record<string, unknown> }> = [];
  for (const record of records) {
    if (record.status !== 'active') continue;
    for (const scope of scopes) {
      const sourcePrefix = drawingScopePrefix(sourceWorkspaceId, scope);
      if (!record.record_id.startsWith(`${sourcePrefix}${INSTRUMENT_MARKER}`)) continue;
      const drawings = (record.payload as { drawings?: unknown }).drawings;
      if (!Array.isArray(drawings) || drawings.length === 0) break;
      const recordId = `${drawingScopePrefix(targetWorkspaceId, scope)}${record.record_id.slice(sourcePrefix.length)}`;
      if (recordId.length <= 200) copies.push({ recordId, payload: { ...record.payload } });
      break;
    }
  }
  return copies;
}

/** Copies a workspace's drawing documents to a duplicate of it. */
export async function copyWorkspaceDrawings(
  sourceWorkspaceId: string,
  targetWorkspaceId: string,
  tabIds: readonly string[],
): Promise<number> {
  const records = await tradingApi.documents('drawings');
  const existing = new Set(records.map((record) => record.record_id));
  const copies = workspaceDrawingCopies(records, sourceWorkspaceId, targetWorkspaceId, tabIds)
    .filter((copy) => !existing.has(copy.recordId));
  await Promise.all(copies.map((copy) => tradingApi.createDocument('drawings', copy.recordId, copy.payload)));
  return copies.length;
}

/**
 * Duplicates the active layout (TVP-2.5): a new workspace from the current one, with its tabs
 * and charts (`createWorkspace` copies the live state), and its drawing documents, copied before
 * the duplicate becomes active so its charts load them. Resolves to the number of drawing
 * documents copied; rejects when the drawings could not be copied.
 */
export async function duplicateTradingWorkspace(
  persistence: Pick<TradingWorkspacePersistence, 'createWorkspace'>,
  name: string,
): Promise<number> {
  const sourceId = currentTradingWorkspaceScopeId();
  const tabIds = useTradingStore.getState().tabs.map((tab) => tab.tabId);
  let copied = 0;
  let failure: unknown = null;
  await persistence.createWorkspace(name, async (targetId) => {
    try {
      copied = await copyWorkspaceDrawings(sourceId, targetId, tabIds);
    } catch (error) {
      failure = error ?? new Error('Drawing copy failed');
    }
  });
  if (failure) throw failure;
  return copied;
}
