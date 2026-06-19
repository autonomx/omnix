import { describe, expect, it, vi } from 'vitest';
import {
  applyRpgItemCommand,
  applyRpgItemResolve,
  applyRpgMerchantCommand,
  applyRpgStructuredItemAction,
  fetchRpgItemDiagnostics,
  fetchRpgItemObjectives,
  runRpgItemMaintenance,
  runRpgItemScenario,
  type RpgItemApiClient,
} from './rpgItemApi';

function fakeClient() {
  const post = vi.fn(async (_path: `/api/${string}`, body: Record<string, unknown>) => ({ ok: true, body }));
  return { client: { post } as RpgItemApiClient, post };
}

describe('rpg item API helpers', () => {
  it('posts item_resolve payloads without undefined fields', async () => {
    const { client, post } = fakeClient();

    await applyRpgItemResolve('session-1', { command: 'use Field Kit', objectiveLimit: 3 }, client);

    expect(post).toHaveBeenCalledWith('/api/rpg/session/get', {
      action: 'item_resolve',
      session_id: 'session-1',
      command: 'use Field Kit',
      objective_limit: 3,
    });
  });

  it('posts text command and structured action payloads', async () => {
    const { client, post } = fakeClient();

    await applyRpgItemCommand('session-1', 'sell Field Kit', client);
    await applyRpgStructuredItemAction('session-1', { action: 'pickup', node_id: 'node-1' }, client);

    expect(post).toHaveBeenNthCalledWith(1, '/api/rpg/session/get', {
      action: 'item_command',
      session_id: 'session-1',
      command: 'sell Field Kit',
    });
    expect(post).toHaveBeenNthCalledWith(2, '/api/rpg/session/get', {
      action: 'item_action',
      session_id: 'session-1',
      item_action: { action: 'pickup', node_id: 'node-1' },
    });
  });

  it('posts planning and diagnostics payloads', async () => {
    const { client, post } = fakeClient();

    await fetchRpgItemObjectives('session-1', { objectiveLimit: 5, station: 'field' }, client);
    await runRpgItemScenario('session-1', { run: true, scenarioLimit: 2, includeStatusSteps: true }, client);
    await fetchRpgItemDiagnostics('session-1', { record: true, recordTrace: true, objectiveLimit: 4 }, client);
    await runRpgItemMaintenance('session-1', { dryRun: true, bucketLimit: 20, recordReport: true }, client);

    expect(post).toHaveBeenNthCalledWith(1, '/api/rpg/session/get', {
      action: 'item_objectives',
      session_id: 'session-1',
      station: 'field',
      objective_limit: 5,
    });
    expect(post).toHaveBeenNthCalledWith(2, '/api/rpg/session/get', {
      action: 'item_scenario',
      session_id: 'session-1',
      scenario_limit: 2,
      include_status_steps: true,
      run: true,
    });
    expect(post).toHaveBeenNthCalledWith(3, '/api/rpg/session/get', {
      action: 'item_diagnostics',
      session_id: 'session-1',
      objective_limit: 4,
      record: true,
      record_trace: true,
    });
    expect(post).toHaveBeenNthCalledWith(4, '/api/rpg/session/get', {
      action: 'item_maintenance',
      session_id: 'session-1',
      dry_run: true,
      bucket_limit: 20,
      record_report: true,
    });
  });

  it('posts merchant command payloads', async () => {
    const { client, post } = fakeClient();

    await applyRpgMerchantCommand(
      'session-1',
      { action: 'buy', itemName: 'Torch', merchantId: 'road-merchant', quantity: 2, source: 'ui' },
      client,
    );

    expect(post).toHaveBeenCalledWith('/api/rpg/session/get', {
      action: 'merchant_command',
      session_id: 'session-1',
      merchant_id: 'road-merchant',
      item_name: 'Torch',
      merchant_action: 'buy',
      quantity: 2,
      source: 'ui',
    });
  });
});
