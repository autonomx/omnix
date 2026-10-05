import type {
  PaperAccount,
  PaperAccountCreateInput,
  PaperAccountSnapshot,
  PaperOrder,
  PaperOrderInput,
  PaperPositionProtection,
  PaperProtectionInput,
  PaperRiskOrderInput,
  PaperRiskOrderResult,
  PaperRiskPreview,
  PaperRiskPreviewInput,
} from './paperTypes';

import { unwrapLabelled } from '../../api/http';
import { api } from './api/gateway';

const paper = <T>(call: Promise<{ data?: T; error?: unknown; response: Response }>) => unwrapLabelled(call, 'Paper Trading');
const orderManagement = { 'X-Omnix-Paper-Order-Management': 'v2' } as const;
const account = (accountId: string) => ({ account_id: accountId });

export const tradingPaperApi = {
  accounts: async (): Promise<PaperAccount[]> =>
    (await paper(api.GET('/api/trading/paper/accounts'))).accounts,
  createAccount: (input: PaperAccountCreateInput): Promise<PaperAccountSnapshot> =>
    paper(api.POST('/api/trading/paper/accounts', { body: input })),
  snapshot: (accountId: string): Promise<PaperAccountSnapshot> =>
    paper(api.GET('/api/trading/paper/accounts/{account_id}', { params: { path: account(accountId) } })),
  riskPreview: (accountId: string, input: PaperRiskPreviewInput): Promise<PaperRiskPreview> =>
    paper(api.POST('/api/trading/paper/accounts/{account_id}/risk-preview', { params: { path: account(accountId) }, body: input })),
  placeRiskOrder: (accountId: string, input: PaperRiskOrderInput): Promise<PaperRiskOrderResult> =>
    paper(api.POST('/api/trading/paper/accounts/{account_id}/risk-orders', { params: { path: account(accountId) }, body: input })),
  placeOrder: (accountId: string, input: PaperOrderInput): Promise<PaperOrder> =>
    paper(api.POST('/api/trading/paper/accounts/{account_id}/orders', { params: { path: account(accountId) }, body: input })),
  cancelOrder: (accountId: string, orderId: string): Promise<PaperOrder> =>
    paper(api.DELETE('/api/trading/paper/accounts/{account_id}/orders/{order_id}', {
      params: { path: { account_id: accountId, order_id: orderId }, header: orderManagement },
    })),
  replaceOrder: (accountId: string, orderId: string, replacement: PaperOrderInput): Promise<{ cancelled: PaperOrder; replacement: PaperOrder }> =>
    paper(api.POST('/api/trading/paper/accounts/{account_id}/orders/{order_id}/replace', {
      params: { path: { account_id: accountId, order_id: orderId }, header: orderManagement },
      body: { replacement },
    })),
  protections: async (accountId: string): Promise<PaperPositionProtection[]> =>
    (await paper(api.GET('/api/trading/paper/accounts/{account_id}/protections', {
      params: { path: account(accountId), query: { active_only: true } },
    }))).protections,
  protection: async (accountId: string, instrumentId: string): Promise<PaperPositionProtection | null> =>
    (await tradingPaperApi.protections(accountId)).find((item) => item.instrument_id === instrumentId) ?? null,
  setProtection: (accountId: string, input: PaperProtectionInput): Promise<PaperPositionProtection> =>
    paper(api.PUT('/api/trading/paper/accounts/{account_id}/protections', { params: { path: account(accountId) }, body: input })),
  clearProtection: (accountId: string, instrumentId: string): Promise<PaperPositionProtection> =>
    paper(api.DELETE('/api/trading/paper/accounts/{account_id}/protections/{instrument_id}', {
      params: { path: { account_id: accountId, instrument_id: instrumentId } },
    })),
  resetAccount: (paperAccount: PaperAccount, initialCash: string): Promise<PaperAccountSnapshot> =>
    paper(api.POST('/api/trading/paper/accounts/{account_id}/reset', {
      params: { path: account(paperAccount.account_id), header: { 'If-Match': paperAccount.revision } },
      body: { initial_cash: initialCash },
    })),
  archiveAccount: (paperAccount: PaperAccount): Promise<PaperAccountSnapshot> =>
    paper(api.DELETE('/api/trading/paper/accounts/{account_id}', {
      params: { path: account(paperAccount.account_id), header: { 'If-Match': paperAccount.revision } },
    })),
};