import type { components } from '../../api/generated/types';

type Schemas = components['schemas'];

// Paper trading payloads as the gateway sends them (WP-9.3).
export type PaperAccount = Schemas['PaperAccount-Output'];
export type PaperBalance = Schemas['PaperBalance-Output'];
export type PaperPosition = Schemas['PaperPosition-Output'];
export type PaperOrder = Schemas['PaperOrder-Output'];
export type PaperFill = Schemas['PaperFill-Output'];
export type PaperLedgerEntry = Schemas['PaperLedgerEntry-Output'];
export type PaperAccountSnapshot = Schemas['PaperAccountSnapshot-Output'];
export type PaperPositionProtection = Schemas['PaperPositionProtection'];
export type PaperRiskPreview = Schemas['PaperRiskPreview'];
export type PaperRiskOrderResult = Schemas['PaperRiskOrderResult'];

export type PaperSide = PaperOrder['side'];
export type PaperOrderType = PaperOrder['order_type'];
export type PaperOrderStatus = PaperOrder['status'];
export type PaperProtectionStatus = PaperPositionProtection['status'];

// What the UI sends.
export type PaperAccountCreateInput = Schemas['PaperAccountCreate'];
export type PaperOrderInput = Schemas['PaperOrderRequest'];
export type PaperProtectionInput = Schemas['PaperProtectionUpsert'];
export type PaperRiskPreviewInput = Schemas['PaperRiskPreviewRequest'];
export type PaperRiskOrderInput = Schemas['PaperRiskOrderRequest'];
